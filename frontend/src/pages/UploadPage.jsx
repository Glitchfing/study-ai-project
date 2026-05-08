import React, { useEffect, useRef, useState } from "react";
import { getNotesList, uploadFile } from "../services/api";

const PIPELINE_STEPS = [
  { icon: "📤", label: "Upload" },
  { icon: "📄", label: "Extract" },
  { icon: "🧹", label: "Clean" },
  { icon: "🔍", label: "Analyze" },
  { icon: "📝", label: "Notes" },
  { icon: "❓", label: "Quiz" },
  { icon: "✅", label: "Done" },
];

export default function UploadPage({ toast, onNavigate, refreshDashboard }) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pipeStep, setPipeStep] = useState(-1);
  const [result, setResult] = useState(null);
  const [uploadHistory, setUploadHistory] = useState([]);
  const inputRef = useRef();

  function refreshUploadHistory() {
    getNotesList()
      .then((notes) => setUploadHistory(notes.filter((note) => note.source === "generated").reverse()))
      .catch(() => setUploadHistory([]));
  }

  useEffect(() => {
    refreshUploadHistory();
  }, []);

  function handleFile(f) {
    if (!f) return;
    setFile(f);
    setResult(null);
    setPipeStep(0);
    toast(`📎 File selected: ${f.name}`, "teal");
  }

  async function processFile() {
    if (!file) return;
    setLoading(true);
    setResult(null);
    // animate pipeline
    for (let i = 0; i < PIPELINE_STEPS.length; i++) {
      setPipeStep(i);
      await new Promise((r) => setTimeout(r, 300 + i * 150));
    }
    try {
      const data = await uploadFile(file);
      setResult(data);
      toast("✅ Processing complete!", "teal");
      refreshUploadHistory();
      if (typeof refreshDashboard === "function") {
        refreshDashboard();
      }
    } catch (e) {
      toast(`❌ Upload failed: ${e.message}`, "coral");
      setPipeStep(-1);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="view active" id="view-upload">
      <div className="section-label">AI Content Pipeline</div>

      {/* Pipeline steps */}
      <div className="pipeline-steps card" style={{ padding: "16px 10px", marginBottom: 16 }}>
        {PIPELINE_STEPS.map((step, i) => (
          <div
            key={step.label}
            className={`pipe-step${pipeStep === i ? " active" : ""}${pipeStep > i ? " done" : ""}`}
          >
            <div className="pipe-circle">{pipeStep > i ? "✓" : step.icon}</div>
            <div className="pipe-label">{step.label}</div>
          </div>
        ))}
      </div>

      <div className="upload-grid">
        {/* Drop zone */}
        <div className="card" style={{ padding: "28px 24px", gridColumn: "1 / -1" }}>
          <div
            className={`upload-zone${dragging ? " drag-over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              handleFile(e.dataTransfer.files[0]);
            }}
            onClick={() => inputRef.current.click()}
          >
            <div className="upload-icon">📂</div>
            <div className="upload-title">
              {file ? file.name : "Drop your file here or click to browse"}
            </div>
            <div className="upload-sub">
              {file
                ? `${(file.size / 1024).toFixed(1)} KB · Ready to process`
                : "Supports PDF, DOCX, TXT, PPT, PNG, JPG"}
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.docx,.txt,.md,.ppt,.pptx,.png,.jpg,.jpeg"
              style={{ display: "none" }}
              onChange={(e) => handleFile(e.target.files[0])}
            />
          </div>

          {file && (
            <div style={{ display: "flex", gap: 10, marginTop: 16, justifyContent: "center" }}>
              <button
                className="btn btn-primary"
                onClick={processFile}
                disabled={loading}
              >
                {loading ? "⏳ Processing…" : "🚀 Process File"}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => { setFile(null); setResult(null); setPipeStep(-1); }}
                disabled={loading}
              >
                ✕ Clear
              </button>
            </div>
          )}
        </div>

        {/* Result */}
        {result && (
          <>
            <div className="card" style={{ padding: "18px 20px" }}>
              <div className="card-title" style={{ marginBottom: 10 }}>📄 Text Preview</div>
              <pre style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                color: "var(--text2)", whiteSpace: "pre-wrap", wordBreak: "break-word",
                maxHeight: 200, overflowY: "auto",
              }}>
                {result.text_preview || "No text extracted."}
              </pre>
            </div>

            <div className="card" style={{ padding: "18px 20px" }}>
              <div className="card-title" style={{ marginBottom: 10 }}>📝 Generated Notes</div>
              <p style={{ color: "var(--text2)", fontSize: 12, marginBottom: 10 }}>
                5 formats generated: Cornell, Outline, Mind Map, Chart, Sentence
              </p>
              <p style={{ color: "var(--muted)", fontSize: 11, marginBottom: 12 }}>
                {result.notes?.total_sections ?? 0} sections saved for future retrieval
              </p>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => onNavigate("notes", { noteId: result.note_id })}
              >
                View in Notes →
              </button>
            </div>

            <div className="card" style={{ padding: "18px 20px" }}>
              <div className="card-title" style={{ marginBottom: 10 }}>❓ Generated Quiz</div>
              <p style={{ color: "var(--text2)", fontSize: 12, marginBottom: 10 }}>
                {result.quiz?.length ?? 0} questions generated from your document
              </p>
              <button
                className="btn btn-coral btn-sm"
                onClick={() => onNavigate("quiz", { quizNoteId: result.note_id })}
              >
                Start Quiz →
              </button>
            </div>
          </>
        )}

        <div className="card" style={{ padding: "18px 20px" }}>
          <div className="card-title" style={{ marginBottom: 10 }}>Saved Uploads</div>
          {uploadHistory.length ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {uploadHistory.map((note) => (
                <div
                  key={note.id}
                  className="tip-row"
                  onClick={() => onNavigate("notes", { noteId: note.id })}
                  style={{ cursor: "pointer" }}
                >
                  <div className="tip-ico">DOC</div>
                  <div className="tip-body">
                    <strong>{note.title}</strong>
                    <br />
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                      {note.total_sections ?? 0} sections · {note.estimated_read_time ?? 0} min read · {note.updated}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: "var(--muted)", fontSize: 12 }}>Uploaded notes will appear here after processing.</div>
          )}
        </div>
      </div>
    </div>
  );
}
