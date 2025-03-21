from fastapi import FastAPI, UploadFile, HTTPException
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
import copy  # Import copy for deep copying

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

# Connect to MongoDB Atlas
try:
    client = MongoClient("mongodb+srv://tharunvankayala:kuchulu2002@cluster0.89xxg.mongodb.net/video_downloader?retryWrites=true&w=majority&appName=Cluster0")
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

async def download_videos(links: List[str]):
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
        "merge_output_format": "mp4",
        "ffmpeg_location": "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
        "verbose": True,
        "noplaylist": True,
    }
    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for link in links:
            try:
                print(f"Starting download for {link}")
                ydl.download([link])
                results.append({"link": link, "status": "success"})
            except Exception as e:
                print(f"Failed to download {link}: {str(e)}")
                results.append({"link": link, "status": "failed", "error": str(e)})
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

    # Read Excel file
    try:
        df = pd.read_excel(temp_file)
        print(f"Columns in Excel file: {df.columns.tolist()}")
        df.columns = df.columns.str.strip().str.lower()
        print(f"Normalized columns: {df.columns.tolist()}")
        if "video_link" not in df.columns:
            raise ValueError("Excel file must contain a 'video_link' column")
        links = df["video_link"].tolist()
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

@app.post("/download-all/")
async def download_all():
    # Fetch links from MongoDB
    links = [item["link"] for item in links_collection.find()]
    if not links:
        raise HTTPException(status_code=400, detail="No video links available. Please upload an Excel file first.")
    
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
        raise HTTPException(status_code=500, detail=f"Error downloading videos: {str(e)}")

@app.post("/download-single/")
async def download_single(link: str):
    if not link:
        raise HTTPException(status_code=400, detail="Please provide a video link.")
    
    try:
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