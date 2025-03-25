import React, { useState, useEffect } from "react";
import axios from "axios";
import axiosRetry from "axios-retry";

interface DownloadResult {
  link: string;
  status: string;
  error?: string;
}

interface ProgressUpdate {
  type: string;
  current?: number;
  total?: number;
  link?: string;
  status?: string;
  error?: string;
  message?: string;
  results?: DownloadResult[];
}

const API_BASE_URL = "https://social-video-downloader-a9d5.onrender.com";

// Configure axios to send cookies with all requests
axios.defaults.withCredentials = true;

// Configure axios to retry requests
axiosRetry(axios, {
  retries: 3,
  retryDelay: (retryCount) => retryCount * 1000,
  retryCondition: (error) => {
    return (
      axiosRetry.isNetworkOrIdempotentRequestError(error) || 
      (error.response?.status !== undefined && error.response.status >= 500)
    );
  },
});

const App: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [singleLink, setSingleLink] = useState("");
  const [bulkResults, setBulkResults] = useState<DownloadResult[]>([]);
  const [singleResult, setSingleResult] = useState<DownloadResult | null>(null);
  const [history, setHistory] = useState<DownloadResult[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loadingBulk, setLoadingBulk] = useState(false);
  const [loadingSingle, setLoadingSingle] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadedFiles, setDownloadedFiles] = useState<string[]>([]);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);

  const fetchDownloadedFiles = async () => {
    try {
      console.log("Fetching downloaded files from:", `${API_BASE_URL}/downloads/list-files/`);
      const response = await axios.get(`${API_BASE_URL}/downloads/list-files/`);
      console.log("Downloaded files response:", response.data);
      setDownloadedFiles(response.data.files);
    } catch (err) {
      console.error("Error fetching downloaded files:", err);
    }
  };

  const fetchHistory = async () => {
    try {
      console.log("Fetching history from:", `${API_BASE_URL}/downloads/history/`);
      const response = await axios.get(`${API_BASE_URL}/downloads/history/`);
      console.log("History response:", response.data);
      setHistory(response.data.downloads);
    } catch (err) {
      console.error("Error fetching history:", err);
    }
  };

  const clearHistory = async () => {
    try {
      await axios.delete(`${API_BASE_URL}/downloads/clear-history/`);
      setHistory([]);
    } catch (err) {
      console.error("Error clearing history:", err);
      setError("Failed to clear download history. Please try again.");
    }
  };

  useEffect(() => {
    fetchDownloadedFiles();
    setBulkResults([]);
    setSingleResult(null);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleUploadAndExtract = async () => {
    if (!file) {
      setError("Please select an Excel file to upload.");
      return;
    }
    setLoadingBulk(true);
    setError(null);
    setBulkResults([]);
    setProgress(null);
  
    const formData = new FormData();
    formData.append("file", file);
  
    try {
      console.log("Uploading Excel file to:", `${API_BASE_URL}/upload-excel/`);
      const uploadResponse = await axios.post(`${API_BASE_URL}/upload-excel/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log("Excel uploaded successfully:", uploadResponse.data);
  
      // Use WebSocket for real-time progress updates with retry logic
      const wsProtocol = API_BASE_URL.startsWith("https") ? "wss" : "ws";
      const wsUrl = `${wsProtocol}://${API_BASE_URL.replace(/^https?:\/\//, "")}/ws/download-all/`;
      
      const connectWebSocket = async (retries = 3, delay = 2000): Promise<WebSocket> => {
        for (let attempt = 1; attempt <= retries; attempt++) {
          try {
            const ws = new WebSocket(wsUrl);
            await new Promise((resolve, reject) => {
              ws.onopen = () => {
                console.log(`WebSocket connection established on attempt ${attempt}`);
                resolve(ws);
              };
              ws.onerror = (error) => {
                console.error(`WebSocket connection failed on attempt ${attempt}:`, error);
                reject(error);
              };
            });
            return ws;
          } catch (error) {
            if (attempt === retries) {
              throw new Error("Max retries reached for WebSocket connection");
            }
            console.log(`Retrying WebSocket connection (${attempt}/${retries}) after ${delay}ms...`);
            await new Promise((resolve) => setTimeout(resolve, delay));
          }
        }
        throw new Error("Failed to establish WebSocket connection after retries");
      };
  
      try {
        const ws = await connectWebSocket();
  
        ws.onmessage = (event) => {
          const data: ProgressUpdate = JSON.parse(event.data);
          console.log("WebSocket message received:", data);
  
          if (data.type === "progress") {
            setProgress(data);
          } else if (data.type === "complete") {
            setBulkResults(data.results || []);
            fetchDownloadedFiles();
            fetchHistory();
            setLoadingBulk(false);
            setProgress(null);
            ws.close();
          } else if (data.type === "error") {
            setError(data.message || "An error occurred during download.");
            setLoadingBulk(false);
            setProgress(null);
            ws.close();
          } else if (data.type === "heartbeat") {
            console.log("Heartbeat received");
          }
        };
  
        ws.onerror = (error) => {
          console.error("WebSocket error:", error);
          setError("WebSocket connection failed. Please try again.");
          setLoadingBulk(false);
          setProgress(null);
        };
  
        ws.onclose = () => {
          console.log("WebSocket connection closed");
        };
  
        // Cleanup on component unmount or error
        return () => {
          ws.close();
        };
      } catch (error) {
        console.error("Failed to establish WebSocket connection after retries:", error);
        setError("Failed to connect to the server for downloading videos. Please try again.");
        setLoadingBulk(false);
      }
    } catch (err: any) {
      console.error("Error in upload and extract:", {
        message: err.message,
        response: err.response ? err.response.data : null,
        status: err.response ? err.response.status : null,
      });
      setError(err.response?.data?.detail || "Failed to upload and extract videos. Please try again.");
      setLoadingBulk(false);
    }
  };
  

  const handleDownloadSingle = async () => {
    if (!singleLink) {
      setError("Please enter a video link.");
      return;
    }
    setLoadingSingle(true);
    setError(null);
    setSingleResult(null);

    try {
      const response = await axios.post(`${API_BASE_URL}/download-single/?link=${encodeURIComponent(singleLink)}`);
      console.log("Single video download response:", response.data);
      setSingleResult(response.data.results[0]);
      fetchDownloadedFiles();
      fetchHistory();
    } catch (err: any) {
      console.error("Error downloading single video:", err.response ? err.response.data : err.message);
      setError(err.response?.data?.detail || "Failed to download video. Please try again.");
    } finally {
      setLoadingSingle(false);
    }
  };

  const handleDownloadAllFiles = () => {
    downloadedFiles.forEach((file) => {
      const link = document.createElement("a");
      link.href = `${API_BASE_URL}/downloads/file/${encodeURIComponent(file)}`;
      link.download = file;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  };

  const toggleHistory = () => {
    if (!showHistory) {
      fetchHistory();
    }
    setShowHistory(!showHistory);
  };

  return (
    <div style={{ padding: "20px", maxWidth: "800px", margin: "0 auto", fontFamily: "Arial, sans-serif" }}>
      <h1 style={{ display: "flex", alignItems: "center", fontSize: "24px", marginBottom: "20px" }}>
        <img src="/logo.png" alt="Logo" style={{ width: "50px", height: "40px" }} /> Social Video Downloader
      </h1>
      <p><b>Download videos from Instagram, X seamlessly</b></p>
      <p><b><u>Note</u>:</b> This service is only to download public account videos </p>
      <p style={{ position: "relative", left: "47px", fontSize: "12px", top: "-12px", color: "rgba(85, 84, 84, 0.76)", fontStyle: "italic" }}>
        (Private accounts are not be downloaded)
      </p>

      <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "10px", boxShadow: "0 2px 5px rgba(0,0,0,0.1)", marginBottom: "20px" }}>
        <h2 style={{ fontSize: "18px", marginBottom: "15px" }}>Bulk Download with Excel</h2>
        <div style={{ border: "2px dashed #ccc", padding: "20px", textAlign: "center", marginBottom: "15px" }}>
          <p style={{ color: "#666", marginBottom: "10px" }}>Upload Excel file with video_link column</p>
          <input
            type="file"
            accept=".xlsx"
            onChange={handleFileChange}
            disabled={loadingBulk}
            style={{ display: "none" }}
            id="file-upload"
          />
          <label
            htmlFor="file-upload"
            style={{
              padding: "10px 20px",
              backgroundColor: "#007bff",
              color: "white",
              borderRadius: "5px",
              cursor: "pointer",
              display: "inline-block",
            }}
          >
            Choose File
          </label>
          <p style={{ marginTop: "10px", color: "#666" }}>{file ? file.name : "No file chosen"}</p>
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button
            onClick={handleUploadAndExtract}
            disabled={!file || loadingBulk}
            style={{
              flex: 1,
              padding: "10px",
              backgroundColor: loadingBulk ? "#ccc" : "#28a745",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: loadingBulk || !file ? "not-allowed" : "pointer",
            }}
          >
            {loadingBulk ? "Processing..." : "Upload & Extract Videos"}
          </button>
        </div>
        {progress && progress.type === "progress" && progress.current && progress.total && (
          <div style={{ marginTop: "20px" }}>
            <p>
              Downloading {progress.current} of {progress.total}: {progress.link} ({progress.status}) -{" "}
              {((progress.current / progress.total) * 100).toFixed(1)}%
            </p>
            <div style={{ backgroundColor: "#eee", borderRadius: "5px", height: "10px" }}>
              <div
                style={{
                  width: `${(progress.current / progress.total) * 100}%`,
                  backgroundColor: "#28a745",
                  height: "100%",
                  borderRadius: "5px",
                }}
              />
            </div>
          </div>
        )}
        {bulkResults.length > 0 && (
          <div style={{ marginTop: "20px" }}>
            <h3>Download Results</h3>
            <ul style={{ listStyleType: "none", padding: 0 }}>
              {bulkResults.map((result, index) => (
                <li
                  key={index}
                  style={{
                    padding: "10px",
                    backgroundColor: result.status === "success" ? "#e6ffe6" : "#ffe6e6",
                    marginBottom: "5px",
                    borderRadius: "5px",
                  }}
                >
                  <strong>{result.link}</strong>:{" "}
                  {result.status === "success" ? "Downloaded" : `Failed (${result.error})`}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "10px", boxShadow: "0 2px 5px rgba(0,0,0,0.1)", marginBottom: "20px" }}>
        <h2 style={{ fontSize: "18px", marginBottom: "15px" }}>Single Video Download</h2>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <input
            type="text"
            value={singleLink}
            onChange={(e) => setSingleLink(e.target.value)}
            placeholder="Paste Instagram or X video link here"
            disabled={loadingSingle}
            style={{
              flex: 1,
              padding: "10px",
              border: "1px solid #ccc",
              borderRadius: "5px",
              fontSize: "14px",
            }}
          />
          <button
            onClick={handleDownloadSingle}
            disabled={loadingSingle}
            style={{
              padding: "10px 20px",
              backgroundColor: loadingSingle ? "#ccc" : "#007bff",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: loadingSingle ? "not-allowed" : "pointer",
            }}
          >
            {loadingSingle ? "Processing..." : "Download"}
          </button>
        </div>
        {singleResult && (
          <div style={{ marginTop: "20px" }}>
            <h3>Download Result</h3>
            <div
              style={{
                padding: "10px",
                backgroundColor: singleResult.status === "success" ? "#e6ffe6" : "#ffe6e6",
                borderRadius: "5px",
              }}
            >
              <strong>{singleResult.link}</strong>:{" "}
              {singleResult.status === "success" ? "Downloaded" : `Failed (${singleResult.error})`}
            </div>
          </div>
        )}
      </div>

      <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "10px", boxShadow: "0 2px 5px rgba(0,0,0,0.1)", marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "15px" }}>
          <h2 style={{ fontSize: "18px", margin: 0 }}>Download Folder</h2>
          <button
            onClick={handleDownloadAllFiles}
            disabled={downloadedFiles.length === 0}
            style={{
              padding: "5px 10px",
              backgroundColor: downloadedFiles.length === 0 ? "#ccc" : "#007bff",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: downloadedFiles.length === 0 ? "not-allowed" : "pointer",
            }}
          >
            Download All
          </button>
        </div>
        {downloadedFiles.length > 0 ? (
          <ul style={{ listStyleType: "none", padding: 0 }}>
            {downloadedFiles.map((file, index) => (
              <li
                key={index}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "10px",
                  borderBottom: "1px solid #eee",
                }}
              >
                <span>📹 {file}</span>
                <div>
                  <span style={{ color: "#666", marginRight: "10px" }}>{(Math.random() * 5).toFixed(1)} MB</span>
                  <a
                    href={`${API_BASE_URL}/downloads/file/${encodeURIComponent(file)}`}
                    download
                    style={{
                      padding: "5px 10px",
                      backgroundColor: "#28a745",
                      color: "white",
                      border: "none",
                      borderRadius: "5px",
                      textDecoration: "none",
                    }}
                  >
                    Download
                  </a>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ color: "#666", textAlign: "center" }}>No files downloaded yet.</p>
        )}
      </div>

      <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "10px", boxShadow: "0 2px 5px rgba(0,0,0,0.1)", marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "15px" }}>
          <button
            onClick={toggleHistory}
            style={{
              padding: "10px 20px",
              backgroundColor: "#007bff",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: "pointer",
            }}
          >
            {showHistory ? "Hide Download History" : "Show Download History"}
          </button>
          {showHistory && (
            <button
              onClick={clearHistory}
              style={{
                padding: "10px 20px",
                backgroundColor: "#dc3545",
                color: "white",
                border: "none",
                borderRadius: "5px",
                cursor: "pointer",
              }}
            >
              Clear Download History
            </button>
          )}
        </div>

        {showHistory && history.length > 0 && (
          <div style={{ marginTop: "20px" }}>
            <h2 style={{ fontSize: "18px", marginBottom: "15px" }}>Download History</h2>
            <ul style={{ listStyleType: "none", padding: 0 }}>
              {history.map((entry, index) => (
                <li
                  key={index}
                  style={{
                    padding: "10px",
                    backgroundColor: entry.status === "success" ? "#e6ffe6" : "#ffe6e6",
                    marginBottom: "5px",
                    borderRadius: "5px",
                  }}
                >
                  <strong>{entry.link}</strong>:{" "}
                  {entry.status === "success" ? "Downloaded" : `Failed (${entry.error})`}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {error && (
        <div style={{ color: "red", marginTop: "20px", textAlign: "center" }}>
          {error}
        </div>
      )}

      <footer style={{ textAlign: "center", marginTop: "20px", color: "#666", fontSize: "14px" }}>
        © 2025 Social Video Downloader. All rights reserved.
      </footer>
    </div>
  );
};

export default App;