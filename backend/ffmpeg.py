# import subprocess

# # Test ffmpeg availability
# try:
#     subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
#     print("ffmpeg is installed and accessible")
# except subprocess.CalledProcessError:
#     print("ffmpeg is not installed or not in PATH")
# except FileNotFoundError:
#     print("ffmpeg is not found in PATH")

import subprocess

# Test ffmpeg availability (mimic yt-dlp's method)
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
    print(f"ffmpeg is installed and accessible: {result.stdout.splitlines()[0]}")
except subprocess.CalledProcessError as e:
    print(f"ffmpeg check failed: {e}")
except FileNotFoundError:
    print("ffmpeg is not found in PATH. Please ensure ffmpeg is installed and added to your PATH.")