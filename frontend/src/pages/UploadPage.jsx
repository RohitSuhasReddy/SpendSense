import { useCallback, useState } from "react";
import { api } from "../api";

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatClassified(classified = {}) {
  return Object.entries(classified)
    .filter(([, count]) => count)
    .map(([method, count]) => `${method}: ${count}`)
    .join(" · ");
}

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
      setError("Please select PDF statements only.");
      return;
    }
    setError("");
    setResults([]);
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name + f.size));
      const next = [...prev];
      for (const file of pdfs) {
        if (!existing.has(file.name + file.size)) next.push(file);
      }
      return next;
    });
  }, []);

  function onDrop(event) {
    event.preventDefault();
    setDragOver(false);
    addFiles(event.dataTransfer.files);
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
    <section className="upload-page">
      <div className="upload-hero">
        <span className="eyebrow">Statement importer</span>
        <h1>Turn statements into useful spending data</h1>
        <p className="muted">Upload Google Pay or credit-card PDFs.</p>
      </div>

      <form className="card upload-card" onSubmit={submit}>
        <div
          className={`dropzone ${dragOver ? "drag-over" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <div className="upload-icon" aria-hidden="true">↑</div>
          <p className="drop-title">Drop your statements here</p>
          <p className="muted drop-copy">PDF only · multiple statements supported</p>
          <label className="file-btn">
            Choose PDF files
            <input
              type="file"
              accept="application/pdf,.pdf"
              multiple
              hidden
              onChange={(event) => {
                addFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </label>
        </div>

        {files.length > 0 && (
          <div className="selected-files">
            <div className="selected-files-head">
              <strong>{files.length} statement{files.length === 1 ? "" : "s"} ready</strong>
              <span className="muted tiny">Review before importing</span>
            </div>
            <ul className="file-list">
              {files.map((file, index) => (
                <li key={file.name + file.size}>
                  <div className="file-meta">
                    <span className="file-type">PDF</span>
                    <div>
                      <strong>{file.name}</strong>
                      <span className="muted tiny">{formatSize(file.size)}</span>
                    </div>
                  </div>
                  <button type="button" className="ghost tiny-btn" onClick={() => removeFile(index)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <button className="upload-submit" type="submit" disabled={files.length === 0 || busy}>
          {busy
            ? `Importing ${files.length} statement${files.length === 1 ? "" : "s"}…`
            : files.length
              ? `Import ${files.length} statement${files.length === 1 ? "" : "s"}`
              : "Choose a statement to continue"}
        </button>

        {error && <div className="status-card error-status">{error}</div>}

        {results.length > 0 && (
          <div className="results-list">
            {results.map((result) =>
              result.ok ? (
                <div key={result.filename} className="status-card success-status">
                  <span className="status-icon">✓</span>
                  <div>
                    <strong>{result.filename}</strong>
                    <p>
                      Imported {result.imported} transaction{result.imported === 1 ? "" : "s"}
                      {result.skipped ? ` · skipped ${result.skipped} duplicate${result.skipped === 1 ? "" : "s"}` : ""}
                      {result.bank_hint ? ` · ${result.bank_hint}` : ""}
                    </p>
                    {formatClassified(result.classified) && (
                      <p className="muted tiny">Classification: {formatClassified(result.classified)}</p>
                    )}
                  </div>
                </div>
              ) : (
                <div key={result.filename} className="status-card error-status">
                  <span className="status-icon">!</span>
                  <div>
                    <strong>{result.filename}</strong>
                    <p>{result.error}</p>
                  </div>
                </div>
              )
            )}
          </div>
        )}
      </form>

      <div className="upload-features">
        <div><strong>Auto-detect</strong><span>GPay vs credit card</span></div>
        <div><strong>Deduplicate</strong><span>Safe monthly re-imports</span></div>
        <div><strong>Cleaner spend</strong><span>UPI Lite top-ups are ignored</span></div>
      </div>
    </section>
  );
}
