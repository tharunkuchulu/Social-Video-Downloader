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

  const BACKEND_URL = "http://localhost:8000"; // Ensure this matches your FastAPI server

  // Fetch download history on component mount
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await axios.get(`${BACKEND_URL}/downloads/`);
        setHistory(response.data.downloads);
      } catch (error: any) {
        console.error("Error fetching history:", error);
        setError("Failed to fetch history. Check console for details.");
      }
    };
    fetchHistory();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post(`${BACKEND_URL}/upload-excel/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResults(response.data.results);
      // Refresh history after upload
      const historyResponse = await axios.get(`${BACKEND_URL}/downloads/`);
      setHistory(historyResponse.data.downloads);
    } catch (error: any) {
      console.error("Error uploading file:", error);
      setResults([{ link: "", status: "failed", error: error.message }]);
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
    <div style={{ padding: "20px" }}>
      <h1>Video Downloader</h1>
      <input type="file" accept=".xlsx" onChange={handleFileChange} />
      <button onClick={handleUpload} disabled={!file || loading}>
        {loading ? "Processing..." : "Upload & Download"}
      </button>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {results.length > 0 && (
        <div>
          <h2>Results</h2>
          <ul>
            {results.map((result, index) => (
              <li key={index}>
                {result.link}: {result.status === "success" ? "Downloaded" : `Failed (${result.error})`}
              </li>
            ))}
          </ul>
        </div>
      )}
      {history.length > 0 && (
        <div>
          <h2>Download History</h2>
          <ul>
            {history.map((entry, index) => (
              <li key={index}>
                {entry.link}: {entry.status === "success" ? "Downloaded" : `Failed (${entry.error})`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default App;