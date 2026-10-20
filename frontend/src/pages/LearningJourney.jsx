import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getPlanner } from "../services/api";
import "../styles/learning-journey.css";

const parseDate = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};
const dateLabel = (value) => {
  const date = parseDate(value);
  return date ? date.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "Date unavailable";
};
const titleFor = (event) => {
  const labels = {
    quiz_completed: "Quiz completed",
    note_view: "Note reviewed",
    study_session_completed: "Study session",
    planner_task_done: "Revision completed",
    planner_task_edited: "Revision updated",
  };
  return labels[event.type] || String(event.title || event.type || "Learning activity").replace(/_/g, " ");
};
const kindFor = (event) => {
  if (event.type === "quiz_completed") return "quiz";
  if (event.type === "note_view") return "note";
  if (event.type === "study_session_completed") return "session";
  return "revision";
};
const topicKey = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export default function LearningJourney({ toast, onNavigate }) {
  const [plan, setPlan] = useState({ events: [], topics: [], tasks: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      setPlan({ events: [], topics: [], tasks: [], summary: {}, ...(await getPlanner() || {}) });
    } catch (err) {
      setError(err?.message || "Could not load your learning history.");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const refresh = () => { if (document.visibilityState === "visible") load(true); };
    const timer = window.setInterval(() => load(true), 30000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  const events = useMemo(() => (plan.events || [])
    .filter((event) => event.source !== "planner" && event.source !== "deadline" && parseDate(event.timestamp))
    .sort((a, b) => (parseDate(b.timestamp)?.getTime() || 0) - (parseDate(a.timestamp)?.getTime() || 0))
    .slice(0, 60), [plan.events]);
  const visible = useMemo(() => events.filter((event) => {
    if (filter === "all") return true;
    if (filter === "notes") return event.type === "note_view";
    if (filter === "quizzes") return event.type === "quiz_completed";
    if (filter === "sessions") return event.type === "study_session_completed";
    if (filter === "revisions") return ["planner_task_done", "planner_task_edited"].includes(event.type);
    return true;
  }), [events, filter]);

  const noteCount = events.filter((event) => event.type === "note_view").length;
  const quizCount = events.filter((event) => event.type === "quiz_completed").length;
  const sessionCount = events.filter((event) => event.type === "study_session_completed").length;

  function openNote(event) {
    const topic = topicKey(event.topic);
    const topicMatch = (plan.topics || []).find((item) => topicKey(item.topic) === topic);
    const noteId = event.note_id || topicMatch?.note_id;
    if (noteId) onNavigate?.("notes", { noteId });
    else toast?.("No matching saved note was linked to this activity.", "coral");
  }

  function practiceAgain(event) {
    const topic = event.topic || "";
    const topicMatch = (plan.topics || []).find((item) => topicKey(item.topic) === topicKey(topic));
    onNavigate?.("quiz", { quizTopic: topic, quizNoteId: event.note_id || topicMatch?.note_id || null });
  }

  return <main className="lj-page lj-simple">
    <header className="lj-page-header">
      <div><span className="lj-overline">YOUR LEARNING HISTORY</span><h1>Your Journey</h1><p>A straightforward record of the notes you reviewed, quizzes you completed and study time you recorded.</p></div>
      <button className="lj-btn subtle" onClick={() => load()} disabled={loading}>Refresh</button>
    </header>

    <p className="lj-simple-summary"><b>{noteCount}</b> note reviews <span>·</span> <b>{quizCount}</b> quiz attempts <span>·</span> <b>{sessionCount}</b> saved study sessions</p>
    <nav className="lj-simple-filters" aria-label="Filter learning activity">
      {[["all", "All activity"], ["notes", "Notes"], ["quizzes", "Quizzes"], ["sessions", "Study sessions"], ["revisions", "Revisions"]].map(([value, label]) =>
        <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{label}</button>
      )}
    </nav>

    {error && <div className="lj-simple-error" role="alert">{error} <button className="lj-btn subtle" onClick={() => load()}>Retry</button></div>}
    {loading ? <p className="lj-simple-muted">Loading saved activity…</p> : visible.length ? <ol className="lj-simple-timeline">
      {visible.map((event) => {
        const kind = kindFor(event);
        const score = event.score != null ? Math.round(Number(event.score)) : (event.total ? Math.round(Number(event.correct || 0) / Number(event.total) * 100) : null);
        const minutes = event.duration_minutes != null ? Number(event.duration_minutes) : (event.duration_seconds != null ? Math.round(Number(event.duration_seconds) / 60) : null);
        return <li className={"lj-simple-event " + kind} key={event.id}>
          <span className="lj-simple-dot" aria-hidden="true"/>
          <article>
            <div className="lj-simple-event-heading"><b>{titleFor(event)}</b><time>{dateLabel(event.timestamp)}</time></div>
            <p>{event.title && event.title !== titleFor(event) ? event.title : event.topic || "Saved learning activity"}</p>
            <div className="lj-simple-event-meta">
              {event.topic && <span>{event.topic}</span>}
              {kind === "quiz" && score != null && <span>Score: {score}%</span>}
              {kind === "session" && minutes != null && <span>{minutes} measured minutes</span>}
            </div>
            <div className="lj-simple-event-actions">
              {kind === "note" && <button className="lj-btn subtle" onClick={() => openNote(event)}>Open note</button>}
              {(kind === "quiz" || kind === "revision") && event.topic && <button className="lj-btn subtle" onClick={() => practiceAgain(event)}>Practice topic</button>}
              {kind === "revision" && <button className="lj-btn subtle" onClick={() => openNote(event)}>Open related note</button>}
            </div>
          </article>
        </li>;
      })}
    </ol> : <div className="lj-simple-empty"><b>No matching activity yet</b><p>Review a saved note, complete a quiz or finish a study session. Your activity will appear here automatically.</p></div>}
  </main>;
}
