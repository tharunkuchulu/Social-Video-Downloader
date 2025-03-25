from fastapi import FastAPI, UploadFile, HTTPException, WebSocket, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import pandas as pd
import yt_dlp
import os
import subprocess
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import asyncio
import logging
import uuid
import re

# Load environment variables from .env file
load_dotenv()

# Set up logging configuration
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS configuration
origins = [
    "http://localhost:5173",
    "https://social-video-downloader-1.onrender.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to handle session cookies
class SessionCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        session_id = request.cookies.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
        request.state.session_id = session_id
        response = await call_next(request)
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=86400,
            samesite="lax",
            secure=True,  # Ensure cookie is sent over HTTPS
        )
        return response

app.add_middleware(SessionCookieMiddleware)

async def get_session_id(request: Request):
    session_id = request.state.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID not found")
    return session_id

# Test ffmpeg availability
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
    logger.info(f"ffmpeg is installed and accessible: {result.stdout.splitlines()[0]}")
except subprocess.CalledProcessError as e:
    logger.error(f"ffmpeg check failed: {e}")
except FileNotFoundError:
    logger.error("ffmpeg is not found in PATH. Please ensure ffmpeg is installed and added to your PATH.")

# Connect to MongoDB Atlas
try:
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client["video_downloader"]
    links_collection = db["links"]
    downloads_collection = db["downloads"]
    logger.info("Connected to MongoDB Atlas successfully")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB Atlas: {str(e)}")
    raise Exception("MongoDB connection failed")

DOWNLOAD_FOLDER = "downloads"

try:
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
except Exception as e:
    logger.error(f"Failed to create downloads folder: {str(e)}")
    raise Exception(f"Failed to create downloads folder: {str(e)}")

def get_platform(link: str) -> str:
    if "instagram.com" in link:
        return "instagram"
    elif "youtu.be" in link or "youtube.com" in link:
        return "youtube"
    elif "x.com" in link or "twitter.com" in link:
        return "x"
    return "unknown"

def sanitize_filename(filename: str) -> str:
    return re.sub(r'[^\w\s-]', '', filename).replace(' ', '_')

def cleanup_downloads_folder(session_id: str):
    MAX_FOLDER_SIZE = 5 * 1024 * 1024 * 1024  # 5GB limit per user
    user_downloads_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    try:
        os.makedirs(user_downloads_dir, exist_ok=True)
        folder_size = sum(
            os.path.getsize(os.path.join(user_downloads_dir, f))
            for f in os.listdir(user_downloads_dir)
            if os.path.isfile(os.path.join(user_downloads_dir, f))
        )
        if folder_size > MAX_FOLDER_SIZE:
            logger.info(f"User {session_id} downloads folder size ({folder_size} bytes) exceeds limit ({MAX_FOLDER_SIZE} bytes). Cleaning up...")
            files = sorted(
                os.listdir(user_downloads_dir),
                key=lambda x: os.path.getmtime(os.path.join(user_downloads_dir, x))
            )
            for file in files:
                file_path = os.path.join(user_downloads_dir, file)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    folder_size -= file_size
                    logger.info(f"Deleted {file_path} ({file_size} bytes) for user {session_id}")
                    if folder_size <= MAX_FOLDER_SIZE:
                        break
    except Exception as e:
        logger.error(f"Error during downloads folder cleanup for user {session_id}: {str(e)}")

async def download_single_video(link: str, ydl_opts: dict, session_id: str, total: int = 1, current: int = 1):
    user_downloads_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    os.makedirs(user_downloads_dir, exist_ok=True)

    def progress_hook(d):
        if d.get('status') == 'finished':
            final_filename = d.get('filename')
            if final_filename:
                base, ext = os.path.splitext(final_filename)
                sanitized_base = sanitize_filename(base)
                new_filename = f"{sanitized_base}.mp4"
                os.rename(final_filename, os.path.join(user_downloads_dir, new_filename))
                logger.info(f"Renamed file to: {new_filename}")

    ydl_opts["outtmpl"] = f"{user_downloads_dir}/%(title)s.%(ext)s"
    ydl_opts["progress_hooks"] = [progress_hook]
    ydl_opts["merge_output_format"] = "mp4"
    ydl_opts["cookiefile"] = "cookies.txt"  # Use cookies file for authentication

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting download for {link} in session {session_id}")
            ydl.download([link])
            files_after = os.listdir(user_downloads_dir)
            logger.info(f"Files in {user_downloads_dir} after download: {files_after}")
            if not files_after:
                raise Exception("No files were created after download")
            result = {"link": link, "status": "success"}
            await downloads_collection.insert_one({"session_id": session_id, "link": link, "status": "success"})
            logger.info(f"Successfully downloaded {link} in session {session_id}")
            return result
    except Exception as e:
        logger.error(f"Failed to download {link} in session {session_id}: {str(e)}")
        result = {"link": link, "status": "failed", "error": str(e)}
        await downloads_collection.insert_one({"session_id": session_id, "link": link, "status": "failed", "error": str(e)})
        return result

async def download_videos(links: List[str], session_id: str):
    total = len(links)
    tasks = []
    for i, link in enumerate(links):
        await asyncio.sleep(0.5)  # Reduced delay to improve performance
        platform = get_platform(link)
        ydl_opts = {
            "verbose": True,
            "noplaylist": True,
            "retries": 20,
            "fragment_retries": 20,
            "abort_on_unavailable_fragments": False,
            "logger": logging.getLogger(),
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
        }
        if platform == "instagram":
            ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best"
            ydl_opts["merge_output_format"] = "mp4"
        else:
            ydl_opts["format"] = "best[height<=720]"
            ydl_opts["merge_output_format"] = "mp4"

        tasks.append(download_single_video(link, ydl_opts, session_id, total, i + 1))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

@app.get("/")
async def root():
    return {"message": "Welcome to the Social Video Downloader API. Visit /docs for API documentation."}

@app.post("/upload-excel/")
async def upload_excel(file: UploadFile):
    if not file.filename.endswith(".xlsx"):
        logger.warning(f"Invalid file format uploaded: {file.filename}")
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx)")

    MAX_FILE_SIZE = 10 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        logger.warning(f"File size exceeds limit: {file.filename} ({len(content)} bytes)")
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

    temp_file = f"temp_{file.filename}"
    try:
        with open(temp_file, "wb") as buffer:
            buffer.write(content)
        logger.info(f"Saved temporary file: {temp_file}")
    except Exception as e:
        logger.error(f"Failed to save uploaded file {file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save the uploaded file. Please try again.")

    try:
        df = pd.read_excel(temp_file, usecols=["video_link"])
        df.columns = df.columns.str.strip().str.lower()
        if "video_link" not in df.columns:
            logger.error("Excel file missing 'video_link' column")
            raise ValueError("Excel file must contain a 'video_link' column")
        links = df["video_link"].dropna().tolist()
        await links_collection.delete_many({})
        await links_collection.insert_many([{"link": link} for link in links])
        logger.info(f"Uploaded Excel file with {len(links)} links")
        return {"links": links}
    except Exception as e:
        logger.error(f"Error reading Excel file {file.filename}: {str(e)}")
        raise HTTPException(status_code=400, detail="Error reading the Excel file. Please ensure it has a 'video_link' column.")
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.info(f"Deleted temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file}: {str(e)}")

@app.post("/download-all/")
async def download_all(session_id: str = Depends(get_session_id)):
    logger.info(f"Received download-all request for session {session_id}")
    links = [item["link"] async for item in links_collection.find({}, {"_id": 0, "link": 1})]
    if not links:
        logger.warning(f"No video links available for download-all in session {session_id}")
        raise HTTPException(status_code=400, detail="No video links available. Please upload an Excel file first.")
    
    try:
        cleanup_downloads_folder(session_id)
        await downloads_collection.delete_many({"session_id": session_id})
        results = await download_videos(links, session_id)
        logger.info(f"Completed download-all with {len(results)} results for session {session_id}: {results}")
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in download-all for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download videos. Please try again.")

@app.post("/download-single/")
async def download_single(link: str = Query(...), session_id: str = Depends(get_session_id)):
    if not link:
        logger.warning(f"No video link provided for download-single in session {session_id}")
        raise HTTPException(status_code=400, detail="Please provide a video link.")
    
    try:
        cleanup_downloads_folder(session_id)
        await downloads_collection.delete_many({"session_id": session_id})
        results = await download_videos([link], session_id)
        logger.info(f"Completed download-single for {link} in session {session_id}: {results}")
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in download-single for {link} in session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download the video. Please try again.")

@app.get("/downloads/list-files/")
async def list_downloaded_files(session_id: str = Depends(get_session_id)):
    try:
        user_downloads_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
        os.makedirs(user_downloads_dir, exist_ok=True)
        files = os.listdir(user_downloads_dir)
        video_files = [
            {"name": f, "size": os.path.getsize(os.path.join(user_downloads_dir, f))}
            for f in files if f.endswith(".mp4")
        ]
        logger.info(f"Listed {len(video_files)} downloaded files for session {session_id}: {[f['name'] for f in video_files]}")
        return {"files": video_files}
    except Exception as e:
        logger.error(f"Error listing files for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list downloaded files. Please try again.")

@app.get("/downloads/file/{filename}")
async def get_file(filename: str, session_id: str = Depends(get_session_id)):
    user_downloads_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    file_path = os.path.join(user_downloads_dir, filename)
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path} for session {session_id}")
        raise HTTPException(status_code=404, detail="File not found")
    logger.info(f"Serving file: {file_path} for session {session_id}")
    return FileResponse(file_path, media_type="video/mp4", filename=filename)

@app.get("/downloads/history/")
async def get_download_history(session_id: str = Depends(get_session_id)):
    try:
        downloads = [item async for item in downloads_collection.find({"session_id": session_id}, {"_id": 0})]
        logger.info(f"Fetched download history with {len(downloads)} entries for session {session_id}: {downloads}")
        return {"downloads": downloads}
    except Exception as e:
        logger.error(f"Error fetching download history for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch download history. Please try again.")

@app.delete("/downloads/clear-history/")
async def clear_download_history(session_id: str = Depends(get_session_id)):
    try:
        await downloads_collection.delete_many({"session_id": session_id})
        logger.info(f"Download history cleared successfully for session {session_id}")
        return {"message": "Download history cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing download history for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to clear download history. Please try again.")

@app.get("/test-download/")
async def test_download(session_id: str = Depends(get_session_id)):
    links = ["https://www.instagram.com/reel/DHLxrgdo0lM/?igsh=dnVvbHBhcTdlNW94"]
    try:
        cleanup_downloads_folder(session_id)
        results = await download_videos(links, session_id)
        logger.info(f"Completed test download with {len(results)} results for session {session_id}: {results}")
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in test download for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to perform test download. Please try again.")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)