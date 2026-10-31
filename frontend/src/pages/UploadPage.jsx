import { useState } from "react";
import { api } from "../api";

export default function UploadPage() {
  const [sourceType, setSourceType] = useState("auto");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await api.uploadPdf(file, sourceType));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Upload statements</h1>
          <p className="muted">Credit card and UPI history are both PDF uploads.</p>
        </div>
      </div>
      <form className="card upload-card" onSubmit={submit}>
        <label>
          Statement type
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            <option value="auto">Auto detect</option>
            <option value="credit_card">Credit card PDF</option>
            <option value="upi">UPI PDF</option>
          </select>
        </label>
        <label>
          PDF file
          <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
        <button type="submit" disabled={!file || busy}>{busy ? "Parsing…" : "Upload and parse"}</button>
        {error && <div className="error">{error}</div>}
        {result && (
          <div className="success">
            Imported {result.imported} transactions from {result.filename}
            {result.bank_hint ? ` (${result.bank_hint})` : ""}. Skipped {result.skipped} duplicates.
          </div>
        )}
      </form>
    </section>
  );
}
