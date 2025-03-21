import React, { useState, useEffect } from "react";
import axios from "axios";

interface DownloadResult {
  link: string;
  status: string;
  error?: string;
}

const App: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [singleLink, setSingleLink] = useState("");
  const [bulkResults, setBulkResults] = useState<DownloadResult[]>([]);
  const [singleResult, setSingleResult] = useState<DownloadResult | null>(null);
  const [history, setHistory] = useState<DownloadResult[]>([]);
  const [showHistory, setShowHistory] = useState(false); // State to control history visibility
  const [loadingBulk, setLoadingBulk] = useState(false);
  const [loadingSingle, setLoadingSingle] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadedFiles, setDownloadedFiles] = useState<string[]>([]);

  // Fetch list of downloaded files
  const fetchDownloadedFiles = async () => {
    try {
      const response = await axios.get("http://localhost:8000/downloads/list-files/");
      setDownloadedFiles(response.data.files);
    } catch (err) {
      console.error("Error fetching downloaded files:", err);
    }
  };

  // Fetch download history
  const fetchHistory = async () => {
    try {
      const response = await axios.get("http://localhost:8000/downloads/history/");
      setHistory(response.data.downloads);
    } catch (err) {
      console.error("Error fetching history:", err);
    }
  };

  useEffect(() => {
    fetchDownloadedFiles();
    // Do not fetch history on initial load; fetch only when the button is clicked
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleUploadExcel = async () => {
    if (!file) {
      setError("Please select an Excel file to upload.");
      return;
    }
    setLoadingBulk(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post("http://localhost:8000/upload-excel/", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log("Excel uploaded:", response.data);
    } catch (err) {
      console.error("Error uploading file:", err);
      setError("Failed to upload file. Please try again.");
    } finally {
      setLoadingBulk(false);
    }
  };

  const handleDownloadAll = async () => {
    setLoadingBulk(true);
    setError(null);
    setBulkResults([]);

    try {
      const response = await axios.post("http://localhost:8000/download-all/");
      setBulkResults(response.data.results);
      fetchDownloadedFiles();
      fetchHistory();
    } catch (err) {
      console.error("Error downloading videos:", err);
      setError("Failed to download videos. Please try again.");
    } finally {
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
      const response = await axios.post("http://localhost:8000/download-single/", { link: singleLink });
      setSingleResult(response.data.results[0]);
      fetchDownloadedFiles();
      fetchHistory();
    } catch (err) {
      console.error("Error downloading single video:", err);
      setError("Failed to download video. Please try again.");
    } finally {
      setLoadingSingle(false);
    }
  };

  const openDownloadsFolder = () => {
    alert("Please navigate to the 'downloads' folder in your backend directory to view the files.");
  };

  const toggleHistory = () => {
    if (!showHistory) {
      fetchHistory(); // Fetch history when showing
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
            onClick={handleUploadExcel}
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
            {loadingBulk ? "Processing..." : "Upload"}
          </button>
          <button
            onClick={handleDownloadAll}
            disabled={loadingBulk}
            style={{
              flex: 1,
              padding: "10px",
              backgroundColor: loadingBulk ? "#ccc" : "#007bff",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: loadingBulk ? "not-allowed" : "pointer",
            }}
          >
            {loadingBulk ? "Processing..." : "Download All"}
          </button>
        </div>
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
            onClick={openDownloadsFolder}
            style={{
              padding: "5px 10px",
              backgroundColor: "#007bff",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: "pointer",
            }}
          >
            Open Folder
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
                    href={`http://localhost:8000/downloads/file/${encodeURIComponent(file)}`}
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
        <button
          onClick={toggleHistory}
          style={{
            padding: "10px 20px",
            backgroundColor: "#007bff",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer",
            width: "100%",
          }}
        >
          {showHistory ? "Hide Download History" : "Show Download History"}
        </button>

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