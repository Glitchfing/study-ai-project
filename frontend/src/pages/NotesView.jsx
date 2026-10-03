import React, { useEffect, useRef, useState } from "react";
import { getAssetUrl, getNotesList, getNote } from "../services/api";

let mermaidModulePromise = null;

function loadMermaid() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import(/* @vite-ignore */ "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs")
      .then((module) => {
        const mermaid = module.default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "dark",
          mindmap: { padding: 16 },
          flowchart: { htmlLabels: false, curve: "basis" },
          themeVariables: {
            background: "transparent",
            primaryColor: "#13505b",
            primaryTextColor: "#edf6f9",
            primaryBorderColor: "#119da4",
            lineColor: "#83c5be",
            secondaryColor: "#0c7489",
            tertiaryColor: "#040404",
          },
        });
        return mermaid;
      });
  }
  return mermaidModulePromise;
}

const FORMAT_LABELS = {
  full: "Reader",
  cornell: "Cornell",
  outline: "Outline",
  mindmap: "Mind Map",
  chart: "Chart",
  sentence: "Sentence",
};

function CornellView({ content }) {
  const cues = content.cue || content.cues || [];
  return (
    <div className="cornell-layout">
      <div className="cornell-cues">
        <div className="cornell-cues-title">Cue Questions</div>
        {cues.map((cue, index) => (
          <div key={index} className="cornell-cue-item">Q. {cue}</div>
        ))}
      </div>
      <div className="cornell-notes">
        <div className="cornell-notes-title">Notes</div>
        <div className="cornell-notes-body" style={{ whiteSpace: "pre-wrap" }}>{content.notes}</div>
      </div>
      <div className="cornell-summary">
        <div className="cornell-summary-title">Summary</div>
        <div>{content.summary}</div>
      </div>
    </div>
  );
}

function renderMindMapNode(node, depth = 0) {
  const name = typeof node === "string" ? node : node?.name;
  const children = typeof node === "string" ? [] : node?.sub_branches || [];
  if (!name) return null;
  return (
    <div key={`${name}-${depth}`} style={{ marginLeft: depth * 18, marginTop: 8 }}>
      <div style={{
        fontFamily: "'Syne', sans-serif",
        fontWeight: 700,
        color: depth === 0 ? "var(--c-bright)" : "var(--text)",
      }}>
        {depth === 0 ? name : `- ${name}`}
      </div>
      {children.map((child) => renderMindMapNode(child, depth + 1))}
    </div>
  );
}

function MermaidDiagram({ code, title = "Rendered diagram" }) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const renderId = useRef(`mermaid-${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    let cancelled = false;
    if (!code?.trim()) return;

    setError("");
    setSvg("");
    loadMermaid()
      .then((mermaid) => mermaid.render(renderId.current, code))
      .then((result) => {
        if (!cancelled) setSvg(result.svg);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Could not render this Mermaid diagram.");
      });

    return () => {
      cancelled = true;
    };
  }, [code]);

  if (!code?.trim()) return null;

  return (
    <div className="mermaid-card">
      <div className="mermaid-title">{title}</div>
      {svg && !error ? (
        <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <div className="mermaid-fallback">
          {error ? <div className="mermaid-error">{error}</div> : <div className="mermaid-loading">Rendering diagram...</div>}
          <pre>{code}</pre>
        </div>
      )}
    </div>
  );
}

function MindMapView({ content }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ color: "var(--muted)", fontSize: 12 }}>
        Root concept: {content.root}
      </div>
      <div>
        {content.branches?.map((branch) => renderMindMapNode(branch, 0))}
      </div>
      {content.mermaid ? (
        <MermaidDiagram code={content.mermaid} title="Mind map" />
      ) : null}
    </div>
  );
}

function OutlineView({ content }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {content.sections?.map((section, index) => (
        <div key={index}>
          <div style={{
            fontFamily: "'Syne', sans-serif",
            fontWeight: 700,
            color: "var(--c-bright)",
            marginBottom: 8,
          }}>
            {section.heading}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {section.points?.map((point, pointIndex) => (
              <div key={pointIndex} style={{ color: "var(--text2)", fontSize: 13 }}>
                {pointIndex + 1}. {point}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function SentenceView({ content }) {
  return (
    <div style={{ color: "var(--text2)", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>
      {content}
    </div>
  );
}

function ChartView({ content }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="study-chart">
        <colgroup>
          <col style={{ width: "24%" }} />
          <col style={{ width: "48%" }} />
          <col style={{ width: "28%" }} />
        </colgroup>
        <thead>
          <tr>
            {content.columns?.map((column, index) => (
              <th key={index}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {content.rows?.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DiagramBlock({ diagram }) {
  return (
    <div style={{
      margin: "18px 0",
      padding: 14,
      border: "1px solid var(--border2)",
      borderRadius: 8,
      background: "rgba(17,157,164,0.08)",
    }}>
      <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, marginBottom: 8 }}>
        {diagram.caption || (diagram.page_number ? `Diagram from page ${diagram.page_number}` : "Diagram")}
      </div>
      {diagram.image_url ? (
        <img
          src={getAssetUrl(diagram.image_url)}
          alt={diagram.caption || "Extracted diagram"}
          style={{
            width: "100%",
            maxHeight: 320,
            objectFit: "contain",
            borderRadius: 10,
            border: "1px solid var(--border)",
            background: "rgba(0,0,0,0.12)",
          }}
        />
      ) : null}
      {diagram.caption ? (
        <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 8 }}>
          Page {diagram.page_number || "source"}
        </div>
      ) : null}
      {diagram.explanation ? (
        <div style={{ color: "var(--text2)", fontSize: 12, lineHeight: 1.7, marginTop: 10 }}>
          {diagram.explanation}
        </div>
      ) : null}
    </div>
  );
}

function NarrativeText({ text, diagrams = [] }) {
  const paragraphs = String(text || "")
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);

  if (!paragraphs.length) return null;

  const firstDiagramIndex = Math.min(1, paragraphs.length);

  return (
    <div className="teaching-narrative">
      {paragraphs.map((paragraph, index) => (
        <React.Fragment key={index}>
          <p>{paragraph}</p>
          {index + 1 === firstDiagramIndex
            ? diagrams.map((diagram, diagramIndex) => (
                <DiagramBlock key={diagram.id || diagramIndex} diagram={diagram} />
              ))
            : null}
        </React.Fragment>
      ))}
      {firstDiagramIndex === 0
        ? diagrams.map((diagram, diagramIndex) => (
            <DiagramBlock key={diagram.id || diagramIndex} diagram={diagram} />
          ))
        : null}
    </div>
  );
}

function StudyAidList({ title, items = [] }) {
  const cleanItems = items.filter(Boolean);
  if (!cleanItems.length) return null;

  return (
    <div className="study-aid-block">
      <div className="study-aid-title">{title}</div>
      <ul>
        {cleanItems.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function SectionStudyAids({ section }) {
  const examples = [
    ...(section.examples || []),
    ...(section.use_cases || []),
  ];

  const hasContent = [
    section.why_this_matters,
    ...(section.definitions || []),
    ...(section.key_points || []),
    ...examples,
    ...(section.important_notes || []),
    ...(section.common_mistakes || []),
    ...(section.revision_notes || []),
    ...(section.memory_tricks || []),
    ...(section.concept_comparisons || []),
    ...(section.test_yourself || []),
  ].filter(Boolean).length;

  if (!hasContent) return null;

  return (
    <div className="study-aids">
      {section.why_this_matters ? (
        <div className="why-card">
          <div className="study-aid-title">Why This Matters</div>
          <p>{section.why_this_matters}</p>
        </div>
      ) : null}
      <div className="study-aid-grid">
        <StudyAidList title="Definitions" items={section.definitions || []} />
        <StudyAidList title="Exam Points" items={section.key_points || []} />
        <StudyAidList title="Examples And Uses" items={examples} />
        <StudyAidList title="Avoid These Mistakes" items={section.common_mistakes || []} />
        <StudyAidList title="Revision Plan" items={section.revision_notes || []} />
        <StudyAidList title="Test Yourself" items={section.test_yourself || []} />
      </div>
      <StudyAidList title="Memory Hooks" items={section.memory_tricks || []} />
      <StudyAidList title="Concept Comparisons" items={section.concept_comparisons || []} />
      <StudyAidList title="Important Notes" items={section.important_notes || []} />
    </div>
  );
}

function FullNoteView({ content }) {
  if (!content.sections?.length) {
    return <CornellView content={content} />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="teaching-summary">
        {content.global_summary}
      </div>

      {content.sections.map((section, index) => (
        <section key={section.section_id || index} className="teaching-section">
          <h2>{section.title}</h2>
          {section.page_numbers?.length ? (
            <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 10 }}>
              Pages: {section.page_numbers.join(", ")}
            </div>
          ) : null}
          <NarrativeText
            text={section.content || section.educational_explanation || section.explanation || section.notes?.cornell?.notes}
            diagrams={section.diagrams || []}
          />
          <SectionStudyAids section={section} />
        </section>
      ))}
    </div>
  );
}

export default function NotesView({ toast, refreshDashboard, selectedNoteId, onNavigate }) {
  const [notesList, setNotesList] = useState([]);
  const [activeNote, setActiveNote] = useState(null);
  const [format, setFormat] = useState("full");
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getNotesList()
      .then((list) => {
        setNotesList(list);
        const targetNote = selectedNoteId
          ? list.find((note) => note.id === selectedNoteId)
          : [...list].reverse().find((note) => note.source === "generated") || list[0];
        if (targetNote) {
          loadNote(targetNote.id, targetNote.source === "generated" ? "full" : "cornell");
        }
      })
      .catch(() => toast("Could not load notes", "coral"));
  }, [selectedNoteId]);

  function loadNote(id, fmt) {
    setLoading(true);
    setActiveNote(id);
    setFormat(fmt);
    getNote(id, fmt)
      .then((data) => {
        setContent(data.content);
        if (typeof refreshDashboard === "function") {
          refreshDashboard();
        }
      })
      .catch(() => toast("Could not load note", "coral"))
      .finally(() => setLoading(false));
  }

  function switchFormat(fmt) {
    if (activeNote) {
      loadNote(activeNote, fmt);
    }
  }

  const activeNoteMeta = notesList.find((note) => note.id === activeNote);
  const canAttemptQuiz = activeNoteMeta?.source === "generated";

  return (
    <div className="view active" id="view-notes">
      <div className="section-label">Your Notes</div>
      <div className="notes-layout">
        <div className="notes-sidebar">
          <div className="card" style={{ padding: "14px 16px", marginBottom: 10 }}>
            <div className="card-title" style={{ marginBottom: 10 }}>My Notes</div>
            {notesList.map((note) => (
              <div
                key={note.id}
                className={`note-item${activeNote === note.id ? " active" : ""}`}
                onClick={() => loadNote(note.id, format)}
              >
                <div style={{ fontWeight: 600, fontSize: 12 }}>{note.title}</div>
                <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                  <span className="tag tag-teal" style={{ fontSize: 9 }}>{note.topic}</span>
                  {" "}Updated {note.updated}
                </div>
              </div>
            ))}
          </div>

          <div className="card" style={{ padding: "14px 16px" }}>
            <div className="card-title" style={{ marginBottom: 10 }}>Note Format</div>
            {Object.entries(FORMAT_LABELS).map(([key, label]) => (
              <div
                key={key}
                className={`format-item${format === key ? " active" : ""}`}
                onClick={() => switchFormat(key)}
              >
                {label}
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: "20px 24px" }}>
          {loading ? (
            <div style={{ color: "var(--muted)", padding: 20 }}>Loading note...</div>
          ) : content ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginBottom: 12 }}>
                <div className="card-title" style={{ fontSize: 15 }}>
                  {content.title || content.document_title}
                </div>
                {canAttemptQuiz ? (
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => onNavigate("quiz", { quizNoteId: activeNote })}
                  >
                    Attempt Quiz
                  </button>
                ) : null}
              </div>
              {content.generation_mode ? (
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 8,
                  padding: "8px 12px",
                  borderRadius: "var(--r)",
                  background: content.generation_mode === "targeted" ? "rgba(17,157,164,0.12)" : "rgba(255,255,255,0.03)",
                  border: "1px solid var(--border)",
                  color: "var(--text2)",
                  fontSize: 11,
                  marginBottom: 16,
                }}>
                  <div>
                    {content.generation_mode === "targeted" ? (
                      <>
                        <strong style={{ color: "var(--c-sky)" }}>⚡ Targeted Topic Study:</strong>{" "}
                        <span>{content.requested_topic || activeNoteMeta?.topic}</span>
                        {content.retrieval?.pages?.length ? (
                          <span style={{ color: "var(--muted)", marginLeft: 6 }}>
                            · Source Pages: {content.retrieval.pages.join(", ")}
                          </span>
                        ) : null}
                      </>
                    ) : (
                      <span>Generation mode: {content.generation_mode}</span>
                    )}
                  </div>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: 10, padding: "3px 8px" }}
                    onClick={() => onNavigate("upload")}
                  >
                    + Study Another Topic
                  </button>
                </div>
              ) : null}
              {format === "full" && <FullNoteView content={content} />}
              {format === "cornell" && <CornellView content={content} />}
              {format === "outline" && <OutlineView content={content} />}
              {format === "mindmap" && <MindMapView content={content} />}
              {format === "chart" && <ChartView content={content} />}
              {format === "sentence" && <SentenceView content={content} />}
            </>
          ) : (
            <div style={{ color: "var(--muted)" }}>Select a note from the list.</div>
          )}
        </div>
      </div>
    </div>
  );
}
