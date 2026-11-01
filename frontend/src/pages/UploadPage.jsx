import { useCallback, useState } from "react";
import { api } from "../api";

export default function UploadPage() {
  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const addFiles = useCallback((fileList) => {
    const pdfs = Array.from(fileList || []).filter(
      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
    if (pdfs.length === 0) {
      setError("Please select PDF files only.");
      return;
    }
    setError("");
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name + f.size));
      const next = [...prev];
      for (const f of pdfs) {
        if (!existing.has(f.name + f.size)) next.push(f);
      }
      return next;
    });
  }, []);

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  }

  function removeFile(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function submit(event) {
    event.preventDefault();
    if (files.length === 0) return;
    setBusy(true);
    setError("");
    setResults([]);
    const outcomes = [];
    try {
      for (const file of files) {
        try {
          const res = await api.uploadPdf(file, "auto");
          outcomes.push({ ok: true, filename: file.name, ...res });
        } catch (err) {
          outcomes.push({ ok: false, filename: file.name, error: err.message });
        }
      }
      setResults(outcomes);
      setFiles([]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Upload statements</h1>
          <p className="muted">
            Drop one or more credit card / UPI PDFs. Type is auto-detected.
          </p>
        </div>
      </div>

      <form className="card upload-card" onSubmit={submit}>
        <div
          className={`dropzone ${dragOver ? "drag-over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <p className="drop-title">Drag & drop PDF files here</p>
          <p className="muted tiny">or click below to choose files</p>
          <label className="file-btn">
            Choose PDFs
            <input
              type="file"
              accept="application/pdf"
              multiple
              hidden
              onChange={(e) => addFiles(e.target.files)}
            />
          </label>
        </div>

        {files.length > 0 && (
          <ul className="file-list">
            {files.map((f, i) => (
              <li key={f.name + f.size}>
                <span>{f.name}</span>
                <button type="button" className="ghost tiny-btn" onClick={() => removeFile(i)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        <button type="submit" disabled={files.length === 0 || busy}>
          {busy ? `Uploading ${files.length} file(s)…` : `Upload & parse ${files.length || ""} PDF(s)`}
        </button>

        {error && <div className="error">{error}</div>}

        {results.length > 0 && (
          <div className="results-list">
            {results.map((r) =>
              r.ok ? (
                <div key={r.filename} className="success">
                  ✓ {r.filename}: imported {r.imported}, skipped {r.skipped}
                  {r.bank_hint ? ` (${r.bank_hint})` : ""}
                </div>
              ) : (
                <div key={r.filename} className="error">
                  ✗ {r.filename}: {r.error}
                </div>
              )
            )}
          </div>
        )}
      </form>
    </section>
  );
}
