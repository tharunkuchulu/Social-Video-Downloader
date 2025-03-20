from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import yt_dlp
import os
from typing import List

app = FastAPI()

# CORS Middleware (already permissive, kept as is)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (e.g., http://localhost:3000)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Folder to save downloaded videos
DOWNLOAD_FOLDER = "downloads"

# Store download history (in-memory for simplicity; use a DB for persistence)
download_history = []

# Ensure the downloads folder exists
try:
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
except Exception as e:
    raise Exception(f"Failed to create downloads folder: {str(e)}")

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
        print(f"Columns in Excel file: {df.columns.tolist()}")  # Debug
        df.columns = df.columns.str.strip().str.lower()  # Normalize column names
        print(f"Normalized columns: {df.columns.tolist()}")  # Debug
        if "video_link" not in df.columns:
            raise ValueError("Excel file must contain a 'video_link' column")
        links = df["video_link"].tolist()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading Excel file: {str(e)}")
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                print(f"Warning: Failed to delete temp file {temp_file}: {str(e)}")

    # Download videos
    try:
        results = await download_videos(links)
        download_history.extend(results)  # Add to history
        return JSONResponse(content={"results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading videos: {str(e)}")

async def download_videos(links: List[str]):
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",  # Best quality MP4
        "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",  # Save to downloads folder
        "merge_output_format": "mp4",  # Ensure MP4 output
    }
    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for link in links:
            try:
                ydl.download([link])
                results.append({"link": link, "status": "success"})
            except Exception as e:
                results.append({"link": link, "status": "failed", "error": str(e)})
    return results

@app.get("/test-download/")
async def test_download():
    links = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]  # Test URL
    results = await download_videos(links)
    download_history.extend(results)  # Add to history
    return JSONResponse(content={"results": results})

@app.get("/downloads/")
async def get_download_history():
    return JSONResponse(content={"downloads": download_history})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)