from pymongo import MongoClient

try:
    client = MongoClient(
        "mongodb+srv://tharunvankayala:kuchulu2002@cluster0.89xxg.mongodb.net/video_downloader?retryWrites=true&w=majority&appName=Cluster0",
        tls=True,
        tlsAllowInvalidCertificates=False
    )
    db = client["video_downloader"]
    print("Connected to MongoDB Atlas successfully")
    print("Databases:", client.list_database_names())
except Exception as e:
    print(f"Failed to connect to MongoDB Atlas: {str(e)}")