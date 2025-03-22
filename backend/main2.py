# from fastapi import FastAPI, UploadFile, HTTPException
# from fastapi.responses import JSONResponse
# from fastapi.middleware.cors import CORSMiddleware
# import pandas as pd
# import yt_dlp
# import os
# import subprocess
# from typing import List

# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Test ffmpeg availability
# try:
#     result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
#     print(f"ffmpeg is installed and accessible: {result.stdout.splitlines()[0]}")
# except subprocess.CalledProcessError as e:
#     print(f"ffmpeg check failed: {e}")
# except FileNotFoundError:
#     print("ffmpeg is not found in PATH. Please ensure ffmpeg is installed and added to your PATH.")

# # Folder to save downloaded videos
# DOWNLOAD_FOLDER = "downloads"

# download_history = []

# # Ensure the downloads folder exists
# try:
#     os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
# except Exception as e:
#     raise Exception(f"Failed to create downloads folder: {str(e)}")

# @app.post("/upload-excel/")
# async def upload_excel(file: UploadFile):
#     if not file.filename.endswith(".xlsx"):
#         raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx)")

#     # Save uploaded file temporarily
#     temp_file = f"temp_{file.filename}"
#     try:
#         # Write the file content to disk
#         content = await file.read()
#         print(f"File size: {len(content)} bytes")  # Debug: Check file size
#         with open(temp_file, "wb") as buffer:
#             buffer.write(content)
#         # Verify the file exists and is accessible
#         if not os.path.exists(temp_file):
#             raise HTTPException(status_code=500, detail="Failed to write temporary file")
#         print(f"Temporary file created: {temp_file}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

#     # Read Excel file
#     try:
#         df = pd.read_excel(temp_file, engine="openpyxl")
#         print(f"Columns in Excel file: {df.columns.tolist()}")
#         df.columns = df.columns.str.strip().str.lower()
#         print(f"Normalized columns: {df.columns.tolist()}")
#         if "video_link" not in df.columns:
#             raise ValueError("Excel file must contain a 'video_link' column")
#         links = df["video_link"].dropna().tolist()  # Drop any NaN values
#         if not links:
#             raise ValueError("No valid video links found in the Excel file")
#         print(f"Extracted links: {links}")
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error reading Excel file: {str(e)}")
#     finally:
#         # Ensure the file is closed before deleting
#         if os.path.exists(temp_file):
#             try:
#                 os.remove(temp_file)
#                 print(f"Temporary file deleted: {temp_file}")
#             except Exception as e:
#                 print(f"Warning: Failed to delete temp file {temp_file}: {str(e)}")

#     # Download videos
#     try:
#         results = await download_videos(links)
#         download_history.extend(results)
#         return JSONResponse(content={"results": results})
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error downloading videos: {str(e)}")

# async def download_videos(links: List[str]):
#     ydl_opts = {
#         "format": "bestvideo+bestaudio/best",
#         "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
#         "merge_output_format": "mp4",
#         "ffmpeg_location": "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
#         "verbose": True,
#         "noplaylist": True,
#         "ignoreerrors": False,
#     }
#     results = []
#     with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#         for link in links:
#             try:
#                 print(f"Starting download for {link}")
#                 ydl.download([link])
#                 results.append({"link": link, "status": "success"})
#             except Exception as e:
#                 error_msg = str(e)
#                 print(f"Failed to download {link}: {error_msg}")
#                 results.append({"link": link, "status": "failed", "error": error_msg})
#     return results

# @app.get("/test-download/")
# async def test_download():
#     links = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
#     try:
#         results = await download_videos(links)
#         download_history.extend(results)
#         return JSONResponse(content={"results": results})
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error in test download: {str(e)}")

# @app.get("/downloads/")
# async def get_download_history():
#     return JSONResponse(content={"downloads": download_history})

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)

import ssl
print(ssl.OPENSSL_VERSION)