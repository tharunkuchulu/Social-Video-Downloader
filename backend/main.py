from fastapi import FastAPI, UploadFile, HTTPException, WebSocket
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
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

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Test ffmpeg availability
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
    print(f"ffmpeg is installed and accessible: {result.stdout.splitlines()[0]}")
except subprocess.CalledProcessError as e:
    print(f"ffmpeg check failed: {e}")
except FileNotFoundError:
    print("ffmpeg is not found in PATH. Please ensure ffmpeg is installed and added to your PATH.")

# Connect to MongoDB Atlas using the connection string from .env
try:
    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client["video_downloader"]
    links_collection = db["links"]
    downloads_collection = db["downloads"]
    print("Connected to MongoDB Atlas successfully")
except Exception as e:
    print(f"Failed to connect to MongoDB Atlas: {str(e)}")
    raise Exception("MongoDB connection failed")

# Folder to save downloaded videos
DOWNLOAD_FOLDER = "downloads"

# Ensure the downloads folder exists
try:
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
except Exception as e:
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

# Function to download a single video with progress updates
async def download_single_video(link: str, ydl_opts: dict, websocket: WebSocket = None, total: int = 1, current: int = 1):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Starting download for {link}")
            ydl.download([link])
            result = {"link": link, "status": "success"}
            if websocket:
                await websocket.send_json({
                    "type": "progress",
                    "current": current,
                    "total": total,
                    "link": link,
                    "status": "success"
                })
            return result
    except Exception as e:
        print(f"Failed to download {link}: {str(e)}")
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
# Async function to download videos in parallel with progress updates
async def download_videos(links: List[str], websocket: WebSocket = None):
    total = len(links)
    results = []
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:  # Limit to 3 concurrent downloads
        tasks = []
        for i, link in enumerate(links):
            # Add a delay to avoid rate-limiting
            await asyncio.sleep(2)  # 2-second delay between downloads

            # Determine the platform and set platform-specific options
            platform = get_platform(link)
            ydl_opts = {
                "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
                "ffmpeg_location": "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
                "verbose": True,
                "noplaylist": True,
                "retries": 20,  # Increased retries for DNS failures
                "fragment_retries": 20,
                "abort_on_unavailable_fragments": False,
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
                loop.run_in_executor(pool, lambda link=link, idx=i+1: asyncio.run(download_single_video(link, ydl_opts, websocket, total, idx)))
            )
        results = await asyncio.gather(*tasks)
    return results

@app.post("/upload-excel/")
async def upload_excel(file: UploadFile):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx)")

    # Save uploaded file temporarily
    temp_file = f"temp_{file.filename}"
    try:
        with open(temp_file, "wb") as buffer:
            buffer.write(await file.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    # Read Excel file with optimized settings
    try:
        df = pd.read_excel(temp_file, usecols=["video_link"])
        df.columns = df.columns.str.strip().str.lower()
        if "video_link" not in df.columns:
            raise ValueError("Excel file must contain a 'video_link' column")
        links = df["video_link"].dropna().tolist()
        # Clear previous links and store new ones in MongoDB
        links_collection.delete_many({})
        links_collection.insert_many([{"link": link} for link in links])
        return JSONResponse(content={"message": "Excel file uploaded successfully", "links": links})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading Excel file: {str(e)}")
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                print(f"Warning: Failed to delete temp file {temp_file}: {str(e)}")

@app.websocket("/ws/download-all/")
async def websocket_download_all(websocket: WebSocket):
    await websocket.accept()
    try:
        # Send a heartbeat message every 10 seconds to keep the connection alive
        async def send_heartbeat():
            while True:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                    await asyncio.sleep(10)
                except Exception as e:
                    print(f"Heartbeat failed: {str(e)}")
                    break

        # Start the heartbeat task
        heartbeat_task = asyncio.create_task(send_heartbeat())

        # Fetch links from MongoDB
        links = [item["link"] for item in links_collection.find({}, {"_id": 0, "link": 1})]
        if not links:
            await websocket.send_json({"type": "error", "message": "No video links available. Please upload an Excel file first."})
            await websocket.close()
            return

        # Download videos and stream progress updates
        results = await download_videos(links, websocket)

        # Save results to MongoDB
        results_copy = copy.deepcopy(results)
        if results:
            downloads_collection.insert_many(results_copy)

        # Send final results
        await websocket.send_json({"type": "complete", "results": results})
        await websocket.close()
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Error downloading videos: {str(e)}"})
        await websocket.close()
    finally:
        heartbeat_task.cancel()

@app.post("/download-all/")
async def download_all():
    # Fetch links from MongoDB
    links = [item["link"] for item in links_collection.find({}, {"_id": 0, "link": 1})]
    if not links:
        raise HTTPException(status_code=400, detail="No video links available. Please upload an Excel file first.")
    
    try:
        # Clear previous download history
        downloads_collection.delete_many({})
        
        results = await download_videos(links)
        # Create a deep copy of results to avoid modification by insert_many
        results_copy = copy.deepcopy(results)
        # Save results to MongoDB
        if results:
            downloads_collection.insert_many(results_copy)
        # Return the original results to avoid ObjectId serialization issues
        return JSONResponse(content={"results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading videos: {str(e)}")

@app.post("/download-single/")
async def download_single(link: str):
    if not link:
        raise HTTPException(status_code=400, detail="Please provide a video link.")
    
    try:
        # Clear previous download history
        downloads_collection.delete_many({})
        
        results = await download_videos([link])
        # Create a deep copy of results to avoid modification by insert_many
        results_copy = copy.deepcopy(results)
        # Save result to MongoDB
        if results:
            downloads_collection.insert_many(results_copy)
        # Return the original results to avoid ObjectId serialization issues
        return JSONResponse(content={"results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading video: {str(e)}")

@app.get("/downloads/list-files/")
async def list_downloaded_files():
    try:
        files = os.listdir(DOWNLOAD_FOLDER)
        video_files = [f for f in files if f.endswith(".mp4")]
        return JSONResponse(content={"files": video_files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

@app.get("/downloads/file/{filename}")
async def get_file(filename: str):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="video/mp4", filename=filename)

@app.get("/downloads/history/")
async def get_download_history():
    try:
        downloads = list(downloads_collection.find({}, {"_id": 0}))
        return JSONResponse(content={"downloads": downloads})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching download history: {str(e)}")

@app.delete("/downloads/clear-history/")
async def clear_download_history():
    try:
        downloads_collection.delete_many({})
        return JSONResponse(content={"message": "Download history cleared successfully"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing download history: {str(e)}")

@app.get("/test-download/")
async def test_download():
    links = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    try:
        results = await download_videos(links)
        # Create a deep copy of results to avoid modification by insert_many
        results_copy = copy.deepcopy(results)
        # Save results to MongoDB
        if results:
            downloads_collection.insert_many(results_copy)
        # Return the original results to avoid ObjectId serialization issues
        return JSONResponse(content={"results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in test download: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)