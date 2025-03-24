from fastapi import FastAPI, UploadFile, HTTPException, WebSocket, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import pandas as pd
import yt_dlp
import os
import subprocess
from typing import List
from pymongo import MongoClient
from bson import ObjectId
import json
import copy
from dotenv import load_dotenv
import asyncio
import concurrent.futures
import time
import logging  # Added for centralized logging
import uuid

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to handle session cookies
class SessionCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get session ID from cookie, or generate a new one if it doesn't exist
        session_id = request.cookies.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Add session_id to request state for use in endpoints
        request.state.session_id = session_id
        
        # Call the next middleware/endpoint
        response = await call_next(request)
        
        # Set the session_id cookie in the response
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=86400,  # Cookie expires after 24 hours
            samesite="lax",
        )
        return response

# Add the session cookie middleware
app.add_middleware(SessionCookieMiddleware)

# Dependency to get the session ID from the request
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

# Connect to MongoDB Atlas using the connection string from .env
try:
    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client["video_downloader"]
    links_collection = db["links"]
    downloads_collection = db["downloads"]
    logger.info("Connected to MongoDB Atlas successfully")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB Atlas: {str(e)}")
    raise Exception("MongoDB connection failed")

# Folder to save downloaded videos
DOWNLOAD_FOLDER = "downloads"

# Ensure the downloads folder exists
try:
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
except Exception as e:
    logger.error(f"Failed to create downloads folder: {str(e)}")
    raise Exception(f"Failed to create downloads folder: {str(e)}")

# Custom JSON encoder to handle ObjectId
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

# Function to determine the platform from the URL
def get_platform(link: str) -> str:
    if "instagram.com" in link:
        return "instagram"
    elif "youtu.be" in link or "youtube.com" in link:
        return "youtube"
    elif "x.com" in link or "twitter.com" in link:
        return "x"
    return "unknown"

# Function to clean up the session-specific downloads folder if it exceeds the size limit
def cleanup_downloads_folder(session_id: str):
    MAX_FOLDER_SIZE = 5 * 1024 * 1024 * 1024  # 5GB limit per user
    user_downloads_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    try:
        # Ensure the user's directory exists
        os.makedirs(user_downloads_dir, exist_ok=True)
        # Calculate the size of the user's downloads directory
        folder_size = sum(
            os.path.getsize(os.path.join(user_downloads_dir, f))
            for f in os.listdir(user_downloads_dir)
            if os.path.isfile(os.path.join(user_downloads_dir, f))
        )
        if folder_size > MAX_FOLDER_SIZE:
            logger.info(f"User {session_id} downloads folder size ({folder_size} bytes) exceeds limit ({MAX_FOLDER_SIZE} bytes). Cleaning up...")
            # Sort files by modification time (oldest first) and delete until under the limit
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

# Function to download a single video with progress updates
async def download_single_video(link: str, ydl_opts: dict, session_id: str, websocket: WebSocket = None, total: int = 1, current: int = 1):
    user_downloads_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    os.makedirs(user_downloads_dir, exist_ok=True)
    ydl_opts["outtmpl"] = f"{user_downloads_dir}/%(title)s.%(ext)s"  # Update the output path to use the session-specific directory
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting download for {link} in session {session_id}")
            ydl.download([link])
            # Verify the file was created
            files_after = os.listdir(user_downloads_dir)
            logger.info(f"Files in {user_downloads_dir} after download: {files_after}")
            result = {"link": link, "status": "success"}
            if websocket:
                await websocket.send_json({
                    "type": "progress",
                    "current": current,
                    "total": total,
                    "link": link,
                    "status": "success"
                })
            logger.info(f"Successfully downloaded {link} in session {session_id}")
            return result
    except Exception as e:
        logger.error(f"Failed to download {link} in session {session_id}: {str(e)}")
        result = {"link": link, "status": "failed", "error": str(e)}
        if websocket:
            await websocket.send_json({
                "type": "progress",
                "current": current,
                "total": total,
                "link": link,
                "status": "failed",
                "error": str(e)
            })
        return result

# Async function to download videos in parallel with progress updates
async def download_videos(links: List[str], session_id: str, websocket: WebSocket = None):
    total = len(links)
    results = []
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:  # Limit to 3 concurrent downloads; adjust based on server resources in production
        tasks = []
        for i, link in enumerate(links):
            # Add a delay to avoid rate-limiting
            await asyncio.sleep(2)  # 2-second delay between downloads

            # Determine the platform and set platform-specific options
            platform = get_platform(link)
            ydl_opts = {
                "verbose": True,
                "noplaylist": True,
                "retries": 20,  # Increased retries for DNS failures
                "fragment_retries": 20,
                "abort_on_unavailable_fragments": False,
                "logger": logging.getLogger(),
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                },  # Add user-agent to avoid rate-limiting
            }
            if platform == "instagram":
                # For Instagram, select the best video and audio streams and merge them
                ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best"  # Adjusted format selector
                ydl_opts["merge_output_format"] = "mp4"  # Ensure the output is mp4
            else:
                # For YouTube and X, use the 720p cap with merging
                ydl_opts["format"] = "best[height<=720]"
                ydl_opts["merge_output_format"] = "mp4"

            tasks.append(
                loop.run_in_executor(pool, lambda link=link, idx=i+1: asyncio.run(download_single_video(link, ydl_opts, session_id, websocket, total, idx)))
            )
        results = await asyncio.gather(*tasks)
    return results

@app.get("/")
async def root():
    return {"message": "Welcome to the Social Video Downloader API. Visit /docs for API documentation."}

@app.post("/upload-excel/")
async def upload_excel(file: UploadFile):
    if not file.filename.endswith(".xlsx"):
        logger.warning(f"Invalid file format uploaded: {file.filename}")
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx)")

    # Add file size validation (10MB limit)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        logger.warning(f"File size exceeds limit: {file.filename} ({len(content)} bytes)")
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

    # Save uploaded file temporarily
    temp_file = f"temp_{file.filename}"
    try:
        with open(temp_file, "wb") as buffer:
            buffer.write(content)
        logger.info(f"Saved temporary file: {temp_file}")
    except Exception as e:
        logger.error(f"Failed to save uploaded file {file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    # Read Excel file with optimized settings
    try:
        df = pd.read_excel(temp_file, usecols=["video_link"])
        df.columns = df.columns.str.strip().str.lower()
        if "video_link" not in df.columns:
            logger.error("Excel file missing 'video_link' column")
            raise ValueError("Excel file must contain a 'video_link' column")
        links = df["video_link"].dropna().tolist()
        # Clear previous links and store new ones in MongoDB
        links_collection.delete_many({})
        links_collection.insert_many([{"link": link} for link in links])
        logger.info(f"Uploaded Excel file with {len(links)} links")
        return JSONResponse(content={"message": "Excel file uploaded successfully", "links": links})
    except Exception as e:
        logger.error(f"Error reading Excel file {file.filename}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error reading Excel file: {str(e)}")
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.info(f"Deleted temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file}: {str(e)}")

@app.websocket("/ws/download-all/")
async def websocket_download_all(websocket: WebSocket, session_id: str = Depends(get_session_id)):
    await websocket.accept()
    try:
        # Send a heartbeat message every 10 seconds to keep the connection alive
        async def send_heartbeat():
            while True:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                    await asyncio.sleep(10)
                except Exception as e:
                    logger.error(f"Heartbeat failed in session {session_id}: {str(e)}")
                    break

        # Start the heartbeat task
        heartbeat_task = asyncio.create_task(send_heartbeat())

        # Fetch links from MongoDB
        links = [item["link"] for item in links_collection.find({}, {"_id": 0, "link": 1})]
        if not links:
            await websocket.send_json({"type": "error", "message": "No video links available. Please upload an Excel file first."})
            await websocket.close()
            return

        # Clean up the user's downloads folder before starting downloads
        cleanup_downloads_folder(session_id)

        # Download videos and stream progress updates
        results = await download_videos(links, session_id, websocket)

        # Save results to MongoDB with session_id
        results_copy = copy.deepcopy(results)
        for result in results_copy:
            result["session_id"] = session_id
        if results:
            downloads_collection.insert_many(results_copy)

        # Send final results
        await websocket.send_json({"type": "complete", "results": results})
        await websocket.close()
    except Exception as e:
        logger.error(f"Error in WebSocket download for session {session_id}: {str(e)}")
        await websocket.send_json({"type": "error", "message": f"Error downloading videos: {str(e)}"})
        await websocket.close()
    finally:
        heartbeat_task.cancel()

@app.post("/download-all/")
async def download_all(session_id: str = Depends(get_session_id)):
    # Fetch links from MongoDB
    links = [item["link"] for item in links_collection.find({}, {"_id": 0, "link": 1})]
    if not links:
        logger.warning(f"No video links available for download-all in session {session_id}")
        raise HTTPException(status_code=400, detail="No video links available. Please upload an Excel file first.")
    
    try:
        # Clean up the user's downloads folder before starting downloads
        cleanup_downloads_folder(session_id)

        # Clear previous download history for this session
        downloads_collection.delete_many({"session_id": session_id})

        results = await download_videos(links, session_id)
        # Create a deep copy of results to avoid modification by insert_many
        results_copy = copy.deepcopy(results)
        # Save results to MongoDB with session_id
        for result in results_copy:
            result["session_id"] = session_id
        if results:
            downloads_collection.insert_many(results_copy)
        logger.info(f"Completed download-all with {len(results)} results for session {session_id}")
        # Return the original results to avoid ObjectId serialization issues
        return JSONResponse(content={"results": results})
    except Exception as e:
        logger.error(f"Error in download-all for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading videos: {str(e)}")

@app.post("/download-single/")
async def download_single(link: str = Query(...), session_id: str = Depends(get_session_id)):
    if not link:
        logger.warning(f"No video link provided for download-single in session {session_id}")
        raise HTTPException(status_code=400, detail="Please provide a video link.")
    
    try:
        # Clean up the user's downloads folder before starting downloads
        cleanup_downloads_folder(session_id)

        # Clear previous download history for this session
        downloads_collection.delete_many({"session_id": session_id})

        results = await download_videos([link], session_id)
        # Create a deep copy of results to avoid modification by insert_many
        results_copy = copy.deepcopy(results)
        # Save result to MongoDB with session_id
        for result in results_copy:
            result["session_id"] = session_id
        if results:
            downloads_collection.insert_many(results_copy)
        logger.info(f"Completed download-single for {link} in session {session_id}")
        # Return the original results to avoid ObjectId serialization issues
        return JSONResponse(content={"results": results})
    except Exception as e:
        logger.error(f"Error in download-single for {link} in session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading video: {str(e)}")

@app.get("/downloads/list-files/")
async def list_downloaded_files(session_id: str = Depends(get_session_id)):
    try:
        user_downloads_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
        os.makedirs(user_downloads_dir, exist_ok=True)
        files = os.listdir(user_downloads_dir)
        video_files = [f for f in files if f.endswith(".mp4")]
        logger.info(f"Listed {len(video_files)} downloaded files for session {session_id}: {video_files}")
        return JSONResponse(content={"files": video_files})
    except Exception as e:
        logger.error(f"Error listing files for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

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
        downloads = list(downloads_collection.find({"session_id": session_id}, {"_id": 0}))
        logger.info(f"Fetched download history with {len(downloads)} entries for session {session_id}")
        return JSONResponse(content={"downloads": downloads})
    except Exception as e:
        logger.error(f"Error fetching download history for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching download history: {str(e)}")

@app.delete("/downloads/clear-history/")
async def clear_download_history(session_id: str = Depends(get_session_id)):
    try:
        downloads_collection.delete_many({"session_id": session_id})
        logger.info(f"Download history cleared successfully for session {session_id}")
        return JSONResponse(content={"message": "Download history cleared successfully"})
    except Exception as e:
        logger.error(f"Error clearing download history for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error clearing download history: {str(e)}")

@app.get("/test-download/")
async def test_download(session_id: str = Depends(get_session_id)):
    links = ["https://www.instagram.com/reel/DHLxrgdo0lM/?igsh=dnVvbHBhcTdlNW94"]
    try:
        # Clean up the user's downloads folder before starting downloads
        cleanup_downloads_folder(session_id)

        results = await download_videos(links, session_id)
        # Create a deep copy of results to avoid modification by insert_many
        results_copy = copy.deepcopy(results)
        # Save results to MongoDB with session_id
        for result in results_copy:
            result["session_id"] = session_id
        if results:
            downloads_collection.insert_many(results_copy)
        logger.info(f"Completed test download with {len(results)} results for session {session_id}")
        # Return the original results to avoid ObjectId serialization issues
        return JSONResponse(content={"results": results})
    except Exception as e:
        logger.error(f"Error in test download for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in test download: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)