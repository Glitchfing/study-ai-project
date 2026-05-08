import React, { useEffect, useState } from "react";
import { getAssetUrl, getNotesList, getNote } from "../services/api";

const FORMAT_LABELS = {
  full: "Reader",
  cornell: "Cornell",
  outline: "Outline",
  mindmap: "Mind Map",
  chart: "Chart",
  sentence: "Sentence",
};

function SectionList({ title, items }) {
  if (!items?.length) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{
        fontSize: 10,
        letterSpacing: 1,
        textTransform: "uppercase",
        color: "var(--muted)",
        marginBottom: 8,
      }}>
        {title}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {items.map((item, index) => (
          <div key={index} style={{ color: "var(--text2)", fontSize: 12, lineHeight: 1.7 }}>
            {index + 1}. {item}
          </div>
        ))}
      </div>
    </div>
  );
}

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
  return (
    <div key={`${node.name}-${depth}`} style={{ marginLeft: depth * 18, marginTop: 8 }}>
      <div style={{
        fontFamily: "'Syne', sans-serif",
        fontWeight: 700,
        color: depth === 0 ? "var(--c-bright)" : "var(--text)",
      }}>
        {depth === 0 ? "Root" : "Node"}: {node.name}
      </div>
      {node.sub_branches?.map((child) => renderMindMapNode(child, depth + 1))}
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
        <div style={{
          border: "1px solid var(--border2)",
          borderRadius: 12,
          padding: 12,
          background: "rgba(17,157,164,0.08)",
        }}>
          <div style={{ fontSize: 10, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)", marginBottom: 8 }}>
            Mermaid Source
          </div>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--text2)", fontSize: 11 }}>
            {content.mermaid}
          </pre>
        </div>
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
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {content.columns?.map((column, index) => (
              <th
                key={index}
                style={{
                  padding: "8px 12px",
                  background: "rgba(17,157,164,0.15)",
                  color: "var(--c-sky)",
                  textAlign: "left",
                  borderBottom: "1px solid var(--border2)",
                  fontFamily: "'Syne', sans-serif",
                }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {content.rows?.map((row, rowIndex) => (
            <tr key={rowIndex} style={{ borderBottom: "1px solid var(--border)" }}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} style={{ padding: "8px 12px", color: "var(--text2)" }}>
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
      marginTop: 14,
      padding: 14,
      border: "1px solid var(--border2)",
      borderRadius: 12,
      background: "rgba(17,157,164,0.08)",
    }}>
      <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, marginBottom: 8 }}>
        Inline Diagram {diagram.page_number ? `- Page ${diagram.page_number}` : ""}
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
          {diagram.caption}
        </div>
      ) : null}
      {diagram.explanation ? (
        <div style={{ color: "var(--text2)", fontSize: 12, lineHeight: 1.7, marginTop: 10 }}>
          {diagram.explanation}
        </div>
      ) : null}
      {diagram.mermaid_code ? (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>
            Mermaid Source
          </div>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--text2)", fontSize: 11 }}>
            {diagram.mermaid_code}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function QuestionGroup({ questions }) {
  if (!questions?.length) return null;

  const grouped = questions.reduce((acc, question) => {
    const type = question.type || "general";
    if (!acc[type]) acc[type] = [];
    acc[type].push(question);
    return acc;
  }, {});

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 10, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)", marginBottom: 10 }}>
        Exam Practice
      </div>
      {Object.entries(grouped).map(([type, items]) => (
        <div key={type} style={{ marginBottom: 12 }}>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, color: "var(--c-bright)", marginBottom: 6 }}>
            {type}
          </div>
          {items.map((question, index) => (
            <div key={index} style={{
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: 10,
              marginBottom: 8,
              background: "rgba(255,255,255,0.02)",
            }}>
              <div style={{ color: "var(--text)", fontSize: 12, marginBottom: 6 }}>
                {index + 1}. {question.question}
              </div>
              {question.options?.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 6 }}>
                  {question.options.map((option, optionIndex) => (
                    <div key={optionIndex} style={{ color: "var(--text2)", fontSize: 11 }}>
                      {String.fromCharCode(65 + optionIndex)}. {option}
                    </div>
                  ))}
                </div>
              ) : null}
              {question.answer_hint ? (
                <div style={{ color: "var(--muted)", fontSize: 11 }}>
                  Hint: {question.answer_hint}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function FullNoteView({ content }) {
  if (!content.sections?.length) {
    return <CornellView content={content} />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ color: "var(--text2)", lineHeight: 1.75 }}>
        {content.global_summary}
      </div>
      {content.recommended_revision_strategy ? (
        <div style={{
          border: "1px solid var(--border2)",
          borderRadius: 12,
          padding: 14,
          background: "rgba(244,140,108,0.08)",
        }}>
          <div style={{ fontSize: 10, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>
            Revision Strategy
          </div>
          <div style={{ color: "var(--text2)", fontSize: 12, lineHeight: 1.7 }}>
            {content.recommended_revision_strategy}
          </div>
        </div>
      ) : null}

      {content.sections.map((section, index) => (
        <section key={section.section_id || index} style={{ borderTop: "1px solid var(--border)", paddingTop: 18 }}>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, color: "var(--text)", marginBottom: 10 }}>
            {index + 1}. {section.title}
          </div>
          {section.page_numbers?.length ? (
            <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 10 }}>
              Pages: {section.page_numbers.join(", ")}
            </div>
          ) : null}
          <div style={{ color: "var(--text2)", lineHeight: 1.8 }}>
            {section.explanation || section.notes?.cornell?.summary}
          </div>

          <SectionList title="Key Points" items={section.key_points} />
          <SectionList title="Definitions" items={section.definitions} />
          <SectionList title="Examples" items={section.examples} />
          <SectionList title="Use Cases" items={section.use_cases} />

          {section.why_this_matters ? (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 10, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>
                Why This Matters
              </div>
              <div style={{ color: "var(--text2)", fontSize: 12, lineHeight: 1.7 }}>
                {section.why_this_matters}
              </div>
            </div>
          ) : null}

          <SectionList title="Important Notes" items={section.important_notes} />
          <SectionList title="Common Mistakes" items={section.common_mistakes} />
          <SectionList title="Test Yourself" items={section.test_yourself} />

          {section.diagrams?.map((diagram, diagramIndex) => (
            <DiagramBlock key={diagram.id || diagramIndex} diagram={diagram} />
          ))}

          <QuestionGroup questions={section.questions} />
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
                <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 16 }}>
                  Generation mode: {content.generation_mode}
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
