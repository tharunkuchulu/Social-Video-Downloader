import pandas as pd

file_path = "C:/Users/Mani/Downloads/Untitled spreadsheet (6).xlsx"
try:
    df = pd.read_excel(file_path, engine="openpyxl")
    print("Columns:", df.columns.tolist())
    df.columns = df.columns.str.strip().str.lower()
    print("Normalized columns:", df.columns.tolist())
    links = df["video_link"].dropna().tolist()
    print("Links:", links)
except Exception as e:
    print(f"Error: {str(e)}")