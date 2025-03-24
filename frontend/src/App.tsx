import React, { useState, useEffect } from "react";
import axios from "axios";

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

const API_BASE_URL = "https://social-video-downloader-a9d5.onrender.com"; // Now used in API calls
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
  const [progress, setProgress] = useState<{ current: number; total: number; link: string; status: string } | null>(null);

  // Fetch list of downloaded files
  const fetchDownloadedFiles = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/downloads/list-files/`);
      setDownloadedFiles(response.data.files);
    } catch (err) {
      console.error("Error fetching downloaded files:", err);
    }
  };
  
  // Fetch download history
  const fetchHistory = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/downloads/history/`);
      setHistory(response.data.downloads);
    } catch (err) {
      console.error("Error fetching history:", err);
    }
  };

  // Clear download history
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

  // @ts-expect-error TS6133: 'connectWebSocket' is declared but its value is never read.
  const connectWebSocket = (retries = 5, delay = 3000): Promise<void> => {
    return new Promise((resolve, reject) => {
      const attemptConnection = (remainingRetries: number) => {
        console.log(`Attempting WebSocket connection (${remainingRetries} retries left)...`);
        const ws = new WebSocket(`wss://video-downloader-backend.onrender.com/ws/download-all/`); // Updated to use wss and Render URL
        ws.onopen = () => {
          console.log("WebSocket connected successfully");
          ws.onmessage = (event) => {
            console.log("WebSocket message received:", event.data);
            const data: ProgressUpdate = JSON.parse(event.data);
            if (data.type === "heartbeat") {
              console.log("Received WebSocket heartbeat");
              return;
            }
            if (data.type === "progress") {
              setProgress({
                current: data.current || 0,
                total: data.total || 0,
                link: data.link || "",
                status: data.status || "",
              });
              if (data.status === "success") {
                setBulkResults((prev) => [...prev, { link: data.link || "", status: "success" }]);
              } else if (data.status === "failed") {
                setBulkResults((prev) => [...prev, { link: data.link || "", status: "failed", error: data.error }]);
              }
            } else if (data.type === "complete") {
              console.log("Download complete:", data.results);
              setLoadingBulk(false);
              fetchDownloadedFiles();
              fetchHistory();
              setProgress(null);
              ws.close();
            } else if (data.type === "error") {
              console.error("WebSocket error message:", data.message);
              setError(data.message || "An error occurred while downloading videos.");
              setLoadingBulk(false);
              setProgress(null);
              ws.close();
            }
          };
          ws.onerror = (err) => {
            console.error("WebSocket connection error:", err);
            if (remainingRetries > 0) {
              console.log(`Retrying WebSocket connection (${remainingRetries} retries left)...`);
              setTimeout(() => attemptConnection(remainingRetries - 1), delay);
            } else {
              reject(new Error("WebSocket connection failed after multiple attempts."));
            }
          };
          ws.onclose = (event) => {
            console.log("WebSocket closed:", event.code, event.reason);
            if (event.code !== 1000) {
              setError("WebSocket connection closed unexpectedly. Please try again.");
              setLoadingBulk(false);
              setProgress(null);
            }
          };
          resolve();
        };
        ws.onerror = (err) => {
          console.error("WebSocket connection error:", err);
          if (remainingRetries > 0) {
            console.log(`Retrying WebSocket connection (${remainingRetries} retries left)...`);
            setTimeout(() => attemptConnection(remainingRetries - 1), delay);
          } else {
            reject(new Error("WebSocket connection failed after multiple attempts."));
          }
        };
      };
      attemptConnection(retries);
    });
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
  
    // Step 1: Upload the Excel file
    const formData = new FormData();
    formData.append("file", file);
  
    try {
      const uploadResponse = await axios.post(`${API_BASE_URL}/upload-excel/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log("Excel uploaded successfully:", uploadResponse.data);
  
      // Use HTTP request with simulated progress (WebSocket temporarily disabled)
      const links = uploadResponse.data.links;
      const total = links.length;
  
      // Simulate progress updates
      for (let i = 0; i < total; i++) {
        setProgress({
          current: i + 1,
          total: total,
          link: links[i],
          status: "downloading",
        });
        await new Promise((resolve) => setTimeout(resolve, 500)); // Simulate delay
      }
  
      try {
        const response = await axios.post(`${API_BASE_URL}/download-all/`);
        console.log("HTTP download response:", response.data);
        setBulkResults(response.data.results);
        fetchDownloadedFiles();
        fetchHistory();
      } catch (httpErr: any) {
        console.error("HTTP download failed:", httpErr.response ? httpErr.response.data : httpErr.message);
        setError(httpErr.response?.data?.detail || "Failed to download videos via HTTP. Please try again.");
      } finally {
        setLoadingBulk(false);
        setProgress(null);
      }
    } catch (err: any) {
      console.error("Error in upload and extract:", err.response ? err.response.data : err.message);
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
        <span style={{ marginRight: "10px" }}>📥</span> Social Video Downloader
      </h1>

      {/* Bulk Download Section */}
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
        {progress && (
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

      {/* Single Video Download Section */}
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

      {/* Download Folder Section */}
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

      {/* Show Download History Button */}
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

        {/* Download History Section */}
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

      {/* Error Message */}
      {error && (
        <div style={{ color: "red", marginTop: "20px", textAlign: "center" }}>
          {error}
        </div>
      )}

      {/* Footer */}
      <footer style={{ textAlign: "center", marginTop: "20px", color: "#666", fontSize: "14px" }}>
        © 2025 Social Video Downloader. All rights reserved.
      </footer>
    </div>
  );
};

export default App;