import React, { useEffect, useRef, useState } from "react";
import {
  getNotesList,
  uploadFiles,
  uploadAndTargetStudy,
  generateTargetedStudy,
  getIndexedDocuments,
} from "../services/api";

const FULL_PIPELINE_STEPS = [
  { icon: "UP", label: "Upload" },
  { icon: "EX", label: "Extract" },
  { icon: "CO", label: "Combine" },
  { icon: "CH", label: "Chunk" },
  { icon: "AI", label: "Understand" },
  { icon: "NO", label: "Notes" },
  { icon: "QZ", label: "Quiz" },
  { icon: "OK", label: "Done" },
];

const TARGETED_PIPELINE_STEPS = [
  { icon: "UP", label: "Upload" },
  { icon: "EX", label: "Extract" },
  { icon: "QD", label: "Index" },
  { icon: "RAG", label: "Topic Search" },
  { icon: "NO", label: "Target Notes" },
  { icon: "QZ", label: "Quiz" },
  { icon: "OK", label: "Done" },
];

const QUICK_TOPICS = [
  "Tokenization",
  "Word Embeddings",
  "N-grams",
  "TF-IDF",
  "Rotation about Pivot Point",
  "2D Transformation",
  "Edge Detection",
];

export default function UploadPage({ toast, onNavigate, refreshDashboard }) {
  const [studyMode, setStudyMode] = useState("targeted"); // "targeted" | "full"
  const [topicPrompt, setTopicPrompt] = useState("");
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pipeStep, setPipeStep] = useState(-1);
  const [result, setResult] = useState(null);
  const [uploadHistory, setUploadHistory] = useState([]);
  const [indexedDocs, setIndexedDocs] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [existingDocTopic, setExistingDocTopic] = useState("");
  const [existingDocLoading, setExistingDocLoading] = useState(false);
  const inputRef = useRef();

  function refreshUploadHistory() {
    getNotesList()
      .then((notes) => setUploadHistory(notes.filter((note) => note.source === "generated").reverse()))
      .catch(() => setUploadHistory([]));

    getIndexedDocuments()
      .then((docs) => {
        setIndexedDocs(docs || []);
        if (docs && docs.length > 0 && !selectedDocId) {
          setSelectedDocId(docs[0].document_id);
        }
      })
      .catch(() => setIndexedDocs([]));
  }

  useEffect(() => {
    refreshUploadHistory();
  }, []);

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;

    setFiles((current) => {
      const seen = new Set(current.map((item) => `${item.name}-${item.size}-${item.lastModified}`));
      const next = [...current];
      incoming.forEach((item) => {
        const key = `${item.name}-${item.size}-${item.lastModified}`;
        if (!seen.has(key)) {
          seen.add(key);
          next.push(item);
        }
      });
      return next;
    });
    setResult(null);
    setPipeStep(0);
    toast(`${incoming.length} file${incoming.length > 1 ? "s" : ""} added`, "teal");
  }

  function removeFile(index) {
    setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setResult(null);
  }

  async function processFiles() {
    if (!files.length) return;

    if (studyMode === "targeted" && !topicPrompt.trim()) {
      toast("Please enter the specific topic or command you want to study.", "coral");
      return;
    }

    setLoading(true);
    setResult(null);

    const steps = studyMode === "targeted" ? TARGETED_PIPELINE_STEPS : FULL_PIPELINE_STEPS;

    for (let i = 0; i < steps.length; i++) {
      setPipeStep(i);
      await new Promise((resolve) => setTimeout(resolve, 240 + i * 90));
    }

    try {
      let data;
      if (studyMode === "targeted") {
        data = await uploadAndTargetStudy(files, topicPrompt.trim());
        toast(`Targeted study for '${topicPrompt.trim()}' generated!`, "teal");
      } else {
        data = await uploadFiles(files);
        toast("Full document processing complete", "teal");
      }
      setResult(data);
      refreshUploadHistory();
      if (typeof refreshDashboard === "function") {
        refreshDashboard();
      }
    } catch (error) {
      toast(`Processing failed: ${error.message}`, "coral");
      setPipeStep(-1);
    } finally {
      setLoading(false);
    }
  }

  async function handleStudyFromExistingDoc() {
    if (!selectedDocId) {
      toast("Please select an indexed document.", "coral");
      return;
    }
    if (!existingDocTopic.trim()) {
      toast("Please enter a topic to study from this document.", "coral");
      return;
    }

    setExistingDocLoading(true);
    try {
      const data = await generateTargetedStudy(selectedDocId, existingDocTopic.trim());
      toast(`Targeted notes for '${existingDocTopic.trim()}' generated!`, "teal");
      setResult(data);
      refreshUploadHistory();
      if (typeof refreshDashboard === "function") {
        refreshDashboard();
      }
    } catch (error) {
      toast(`Targeted retrieval failed: ${error.message}`, "coral");
    } finally {
      setExistingDocLoading(false);
    }
  }

  const activeSteps = studyMode === "targeted" ? TARGETED_PIPELINE_STEPS : FULL_PIPELINE_STEPS;

  return (
    <div className="view active" id="view-upload">
      <div className="section-label">Intelligent Document Learning & Targeted Study</div>

      {/* Pipeline steps indicator */}
      <div className="pipeline-steps card" style={{ padding: "16px 10px", marginBottom: 16 }}>
        {activeSteps.map((step, index) => (
          <div
            key={step.label}
            className={`pipe-step${pipeStep === index ? " active" : ""}${pipeStep > index ? " done" : ""}`}
          >
            <div className="pipe-circle">{pipeStep > index ? "✓" : step.icon}</div>
            <div className="pipe-label">{step.label}</div>
          </div>
        ))}
      </div>

      <div className="upload-grid">
        {/* Main Upload Card */}
        <div className="card" style={{ padding: "24px 22px", gridColumn: "1 / -1" }}>

          {/* Mode Selector Tabs */}
          <div style={{
            display: "flex",
            gap: 12,
            marginBottom: 20,
            padding: 4,
            background: "var(--bg2)",
            borderRadius: "var(--r)",
            border: "1px solid var(--border)",
          }}>
            <button
              type="button"
              onClick={() => setStudyMode("targeted")}
              style={{
                flex: 1,
                padding: "10px 16px",
                borderRadius: "var(--r)",
                border: "none",
                background: studyMode === "targeted" ? "var(--c-bright)" : "transparent",
                color: studyMode === "targeted" ? "var(--c-deep)" : "var(--text)",
                fontWeight: 700,
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                transition: "var(--transition)",
              }}
            >
              <span>⚡</span> Topic-Targeted Study (Fast RAG)
            </button>
            <button
              type="button"
              onClick={() => setStudyMode("full")}
              style={{
                flex: 1,
                padding: "10px 16px",
                borderRadius: "var(--r)",
                border: "none",
                background: studyMode === "full" ? "var(--c-bright)" : "transparent",
                color: studyMode === "full" ? "var(--c-deep)" : "var(--text)",
                fontWeight: 700,
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                transition: "var(--transition)",
              }}
            >
              <span>📖</span> Full Document Study (Complete Book)
            </button>
          </div>

          {/* Targeted Study Topic Prompt Section */}
          {studyMode === "targeted" && (
            <div style={{
              background: "rgba(17, 157, 164, 0.08)",
              border: "1px solid var(--border2)",
              borderRadius: "var(--r)",
              padding: "18px 20px",
              marginBottom: 20,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 16 }}>🎯</span>
                <strong style={{ fontSize: 14, color: "var(--text)" }}>
                  What topic or section would you like to study?
                </strong>
              </div>
              <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 12, lineHeight: 1.4 }}>
                StudyAI will extract and index your document once into Qdrant, then semantically retrieve and generate study notes <strong>strictly for the requested topic</strong> without loading or re-generating the entire book.
              </p>

              <div style={{ position: "relative", marginBottom: 10 }}>
                <input
                  type="text"
                  placeholder="e.g. Tokenization, N-grams, Word Embeddings, Rotation about pivot point..."
                  value={topicPrompt}
                  onChange={(e) => setTopicPrompt(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "12px 16px",
                    background: "var(--bg)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--r)",
                    color: "var(--text)",
                    fontSize: 13,
                    outline: "none",
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && files.length && topicPrompt.trim()) {
                      processFiles();
                    }
                  }}
                />
              </div>

              {/* Quick suggestions chips */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, color: "var(--muted)" }}>Quick picks:</span>
                {QUICK_TOPICS.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => setTopicPrompt(tag)}
                    style={{
                      background: topicPrompt === tag ? "var(--c-bright)" : "var(--glass)",
                      color: topicPrompt === tag ? "var(--c-deep)" : "var(--text2)",
                      border: "1px solid var(--border)",
                      borderRadius: 12,
                      padding: "3px 10px",
                      fontSize: 11,
                      cursor: "pointer",
                    }}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Dropzone */}
          <div
            className={`upload-zone${dragging ? " drag-over" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              addFiles(event.dataTransfer.files);
            }}
            onClick={() => inputRef.current.click()}
          >
            <div className="upload-icon">+</div>
            <div className="upload-title">
              {files.length
                ? `${files.length} file${files.length > 1 ? "s" : ""} selected for ${studyMode === "targeted" ? "targeted topic extraction" : "full study"}`
                : "Drop your PDF, Textbook, or Notes here"}
            </div>
            <div className="upload-sub">
              Supports large books, lecture slides, and handwritten notes (PDF, DOCX, PPTX, TXT)
            </div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".pdf,.doc,.docx,.txt,.md,.ppt,.pptx,.png,.jpg,.jpeg"
              style={{ display: "none" }}
              onChange={(event) => {
                addFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </div>

          {/* Files List & Action Buttons */}
          {files.length > 0 ? (
            <>
              <div className="file-stack" style={{ marginTop: 16 }}>
                {files.map((item, index) => (
                  <div className="file-pill" key={`${item.name}-${item.size}-${item.lastModified}`}>
                    <div className="file-pill-main">
                      <strong>{item.name}</strong>
                      <span>{(item.size / 1024).toFixed(1)} KB</span>
                    </div>
                    <button
                      className="icon-btn"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        removeFile(index);
                      }}
                      disabled={loading}
                      title="Remove file"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>

              <div style={{ display: "flex", gap: 10, marginTop: 18, justifyContent: "center", flexWrap: "wrap" }}>
                <button className="btn btn-secondary" onClick={() => inputRef.current.click()} disabled={loading}>
                  + Add File
                </button>
                <button className="btn btn-primary" onClick={processFiles} disabled={loading}>
                  {loading
                    ? "Processing with RAG..."
                    : studyMode === "targeted"
                    ? `⚡ Generate Targeted Notes for "${topicPrompt || "Topic"}"`
                    : `Process Full Document (${files.length} File${files.length > 1 ? "s" : ""})`}
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    setFiles([]);
                    setResult(null);
                    setPipeStep(-1);
                  }}
                  disabled={loading}
                >
                  Clear
                </button>
              </div>
            </>
          ) : null}
        </div>

        {/* Existing Indexed Document Study Launcher */}
        {indexedDocs.length > 0 && (
          <div className="card" style={{ padding: "20px 22px", gridColumn: "1 / -1" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 16 }}>📚</span>
              <strong style={{ fontSize: 14, color: "var(--text)" }}>
                Study a New Topic from an Already-Uploaded Document
              </strong>
            </div>
            <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14 }}>
              These documents are already indexed in Qdrant. Select one and enter a new topic command to instantly retrieve and study that section without uploading again!
            </p>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <select
                value={selectedDocId}
                onChange={(e) => setSelectedDocId(e.target.value)}
                style={{
                  padding: "10px 14px",
                  borderRadius: "var(--r)",
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  fontSize: 12,
                  minWidth: 220,
                  outline: "none",
                }}
              >
                {indexedDocs.map((doc) => (
                  <option key={doc.document_id} value={doc.document_id}>
                    📄 {doc.filename} {doc.page_count ? `(${doc.page_count} pages)` : ""}
                  </option>
                ))}
              </select>

              <input
                type="text"
                placeholder="Enter topic prompt (e.g., Tokenization, N-grams)..."
                value={existingDocTopic}
                onChange={(e) => setExistingDocTopic(e.target.value)}
                style={{
                  flex: 1,
                  minWidth: 200,
                  padding: "10px 14px",
                  borderRadius: "var(--r)",
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  fontSize: 12,
                  outline: "none",
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleStudyFromExistingDoc();
                }}
              />

              <button
                className="btn btn-primary"
                onClick={handleStudyFromExistingDoc}
                disabled={existingDocLoading || !existingDocTopic.trim()}
              >
                {existingDocLoading ? "Retrieving & Generating..." : "⚡ Study Topic"}
              </button>
            </div>
          </div>
        )}

        {/* Results Preview */}
        {result ? (
          <>
            <div className="card" style={{ padding: "18px 20px" }}>
              <div className="card-title" style={{ marginBottom: 10 }}>
                {result.mode === "targeted" ? `🎯 Topic: ${result.topic}` : "Text Preview"}
              </div>
              <p style={{ color: "var(--muted)", fontSize: 11, marginBottom: 10 }}>
                Session {result.session_id?.slice(0, 8)} · Mode: <strong>{result.generation_mode || "targeted"}</strong>
                {result.retrieval?.pages && ` · Source Pages: ${result.retrieval.pages.join(", ")}`}
              </p>
              <pre style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 11,
                color: "var(--text2)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                maxHeight: 200,
                overflowY: "auto",
              }}>
                {result.notes?.global_summary || result.text_preview || "Targeted study synthesized successfully."}
              </pre>
            </div>

            <div className="card" style={{ padding: "18px 20px" }}>
              <div className="card-title" style={{ marginBottom: 10 }}>Generated Notes</div>
              <p style={{ color: "var(--text2)", fontSize: 12, marginBottom: 10 }}>
                Cornell, Outline, Mind Map, Chart, and Sentence notes generated specifically for this topic.
              </p>
              <p style={{ color: "var(--muted)", fontSize: 11, marginBottom: 12 }}>
                {result.notes?.total_sections ?? 1} section(s) ready to review.
              </p>
              <button className="btn btn-primary btn-sm" onClick={() => onNavigate("notes", { noteId: result.note_id })}>
                View in Notes
              </button>
            </div>

            <div className="card" style={{ padding: "18px 20px" }}>
              <div className="card-title" style={{ marginBottom: 10 }}>Generated Quiz</div>
              <p style={{ color: "var(--text2)", fontSize: 12, marginBottom: 10 }}>
                Topic-grounded questions ready for testing your understanding.
              </p>
              <button className="btn btn-coral btn-sm" onClick={() => onNavigate("quiz", { quizNoteId: result.note_id })}>
                Start Quiz
              </button>
            </div>
          </>
        ) : null}

        {/* Saved Uploads List */}
        <div className="card" style={{ padding: "18px 20px", gridColumn: "1 / -1" }}>
          <div className="card-title" style={{ marginBottom: 10 }}>Saved Study Sessions</div>
          {uploadHistory.length ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {uploadHistory.map((note) => (
                <div
                  key={note.id}
                  className="tip-row"
                  onClick={() => onNavigate("notes", { noteId: note.id })}
                  style={{ cursor: "pointer" }}
                >
                  <div className="tip-ico">
                    {note.topic?.toLowerCase().includes("targeted") || note.title?.toLowerCase().includes("targeted") ? "🎯" : "DOC"}
                  </div>
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
            <div style={{ color: "var(--muted)", fontSize: 12 }}>Uploaded study sessions will appear here after processing.</div>
          )}
        </div>
      </div>
    </div>
  );
}
