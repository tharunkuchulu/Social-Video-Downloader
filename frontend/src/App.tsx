import React, { useState, useEffect } from "react";
import axios from "axios";

interface DownloadResult {
  link: string;
  status: string;
  error?: string;
}

const App: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [results, setResults] = useState<DownloadResult[]>([]);
  const [history, setHistory] = useState<DownloadResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const BACKEND_URL = "http://localhost:8000";

  // Fetch download history on component mount
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await axios.get(`${BACKEND_URL}/downloads/`);
        setHistory(response.data.downloads || []);
      } catch (error: any) {
        console.error("Error fetching history:", error);
        setError("Failed to fetch history. Check console for details.");
      }
    };
    fetchHistory();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select an Excel file to upload.");
      return;
    }
    setLoading(true);
    setError(null);
    setResults([]);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post(`${BACKEND_URL}/upload-excel/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResults(response.data.results || []);
      // Refresh history after upload
      const historyResponse = await axios.get(`${BACKEND_URL}/downloads/`);
      setHistory(historyResponse.data.downloads || []);
    } catch (error: any) {
      console.error("Error uploading file:", error);
      if (error.response) {
        setError(`Server error: ${error.response.status} - ${error.response.data.detail}`);
      } else if (error.request) {
        setError("CORS or network error: No response from server. Check backend URL and CORS settings.");
      } else {
        setError("Error: " + error.message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "20px", maxWidth: "600px", margin: "0 auto" }}>
      <h1>Video Downloader</h1>
      <div style={{ marginBottom: "20px" }}>
        <label htmlFor="file-upload" style={{ display: "block", marginBottom: "10px" }}>
          Upload Excel File (.xlsx):
        </label>
        <input
          id="file-upload"
          type="file"
          accept=".xlsx"
          onChange={handleFileChange}
          disabled={loading}
          style={{ marginBottom: "10px" }}
        />
        <button
          onClick={handleUpload}
          disabled={!file || loading}
          style={{
            padding: "10px 20px",
            backgroundColor: loading ? "#ccc" : "#007bff",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: loading || !file ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Processing..." : "Upload & Download"}
        </button>
      </div>
      {error && (
        <div style={{ color: "red", marginBottom: "20px" }}>
          {error}
        </div>
      )}
      {results.length > 0 && (
        <div>
          <h2>Download Results</h2>
          <ul style={{ listStyleType: "none", padding: 0 }}>
            {results.map((result, index) => (
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
      {history.length > 0 && (
        <div>
          <h2>Download History</h2>
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
  );
};

export default App;