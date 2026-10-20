import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  autoSchedule, completeStudySession, getActiveStudySession, getPlanner,
  startStudySession, toggleTask, updatePlannerTask,
} from "../services/api";
import "../styles/revision-planner.css";

const done = (task) => Boolean(task?.done) || task?.status === "completed";
const cancelled = (task) => ["cancelled", "skipped"].includes(task?.status);
const dateOf = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};
const localInput = (value) => {
  const date = dateOf(value);
  return date ? new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
};
const formatDate = (value) => {
  const date = dateOf(value);
  return date ? date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "Not scheduled";
};
const durationOf = (task) => {
  if (Number(task?.duration_minutes) > 0) return Number(task.duration_minutes);
  const value = String(task?.est || "");
  const minutes = value.match(/(\d+)\s*min/i);
  if (minutes) return Number(minutes[1]);
  const hours = value.match(/(\d+)\s*h/i);
  return hours ? Number(hours[1]) * 60 : 20;
};
const isOverdue = (task, now = Date.now()) => {
  if (done(task) || cancelled(task)) return false;
  const scheduled = dateOf(task?.scheduled_at);
  const due = dateOf(task?.original_due_date || task?.due_date);
  const dueDateOnly = typeof (task?.original_due_date || task?.due_date) === "string" && /^\d{4}-\d{2}-\d{2}$/.test(task.original_due_date || task.due_date);
  return Boolean((scheduled && scheduled.getTime() < now) || (due && (dueDateOnly ? due.toDateString() !== new Date(now).toDateString() && due < new Date(now) : due.getTime() < now)));
};
const readableReason = (task) => task?.priority_reason || (task?.evidence?.mastery_pct != null
  ? `Quiz evidence shows ${Math.round(task.evidence.mastery_pct)}% mastery.`
  : task?.activity_type === "assessment"
    ? "This topic has notes but needs a quiz attempt to measure mastery."
    : "Suggested from your saved notes and revision plan.");

export default function RevisionPlanner({ toast, refreshDashboard, onNavigate }) {
  const [plan, setPlan] = useState({ tasks: [], topics: [], summary: {} });
  const [activeSession, setActiveSession] = useState(null);
  const [clock, setClock] = useState(Date.now());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [rescheduleId, setRescheduleId] = useState(null);
  const [rescheduleAt, setRescheduleAt] = useState("");

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      const [nextPlan, session] = await Promise.all([
        getPlanner(),
        getActiveStudySession().catch(() => ({ active: null })),
      ]);
      setPlan({ tasks: [], topics: [], summary: {}, ...(nextPlan || {}) });
      setActiveSession(session?.active || null);
    } catch (err) {
      setError(err?.message || "Could not load your revision plan.");
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

  useEffect(() => {
    if (!activeSession) return undefined;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeSession?.session_id, activeSession?.status, activeSession?.active_interval_started_at]);

  const tasks = plan.tasks || [];
  const pending = useMemo(() => tasks
    .filter((task) => !done(task) && !cancelled(task))
    .sort((a, b) => {
      const rank = { high: 0, med: 1, low: 2 };
      const priority = (rank[a.priority] ?? 1) - (rank[b.priority] ?? 1);
      if (priority) return priority;
      return (dateOf(a.scheduled_at)?.getTime() ?? Number.MAX_SAFE_INTEGER) -
        (dateOf(b.scheduled_at)?.getTime() ?? Number.MAX_SAFE_INTEGER);
    }), [tasks]);
  const overdueCount = pending.filter((task) => isOverdue(task)).length;
  const nextTask = pending.find((task) => isOverdue(task)) || pending[0] || null;
  const sessionSeconds = activeSession
    ? Math.max(0, Number(activeSession.duration_seconds) || 0) +
      (activeSession.status === "active" && activeSession.active_interval_started_at
        ? Math.max(0, Math.floor((clock - (dateOf(activeSession.active_interval_started_at)?.getTime() || clock)) / 1000))
        : 0)
    : 0;

  const notify = (message, tone = "teal") => toast?.(message, tone);

  async function generatePlan() {
    setBusy("generate");
    try {
      const result = await autoSchedule();
      await load();
      await refreshDashboard?.();
      notify(result?.topics_considered
        ? "Revision plan updated from your saved notes and quiz results."
        : "No topics to schedule yet. Upload a note or complete a quiz first.", result?.topics_considered ? "teal" : "coral");
    } catch (err) {
      notify(err?.message || "Could not update the revision plan.", "coral");
    } finally { setBusy(""); }
  }

  async function markDone(task) {
    setBusy("done-" + task.id);
    try {
      await toggleTask(task.id, true);
      await load();
      await refreshDashboard?.();
      notify("Revision marked complete.");
    } catch (err) {
      notify(err?.message || "Could not update this task.", "coral");
    } finally { setBusy(""); }
  }

  async function startSession(task) {
    if (!task?.topic) return notify("This task has no linked topic yet.", "coral");
    setBusy("start-" + task.id);
    try {
      const result = await startStudySession(task.topic, task.id);
      const session = result?.session || result?.active || null;
      setActiveSession(session);
      if (result?.already_active) {
        notify("A study session is already active. Finish it before starting another.", "coral");
        return;
      }
      if (!done(task)) await updatePlannerTask(task.id, { status: "in_progress" });
      await load();
      notify("Study session started for " + task.topic + ".");
    } catch (err) {
      notify(err?.message || "Could not start the study session.", "coral");
    } finally { setBusy(""); }
  }

  async function finishSession() {
    if (!activeSession?.session_id) return;
    setBusy("finish");
    try {
      const result = await completeStudySession(activeSession.session_id);
      const seconds = Number(result?.session?.duration_seconds) || 0;
      setActiveSession(null);
      await load();
      await refreshDashboard?.();
      notify("Study session saved · " + Math.floor(seconds / 60) + " measured minutes.");
    } catch (err) {
      notify(err?.message || "Could not save the study session.", "coral");
    } finally { setBusy(""); }
  }

  async function saveReschedule(task) {
    const date = dateOf(rescheduleAt);
    if (!date || date.getTime() <= Date.now()) return notify("Choose a future date and time.", "coral");
    setBusy("reschedule-" + task.id);
    try {
      await updatePlannerTask(task.id, { scheduled_at: date.toISOString() });
      setRescheduleId(null);
      setRescheduleAt("");
      await load();
      await refreshDashboard?.();
      notify("Revision rescheduled.");
    } catch (err) {
      notify(err?.message || "Could not reschedule this task.", "coral");
    } finally { setBusy(""); }
  }

  const openNote = (task) => {
    if (task.note_id) onNavigate?.("notes", { noteId: task.note_id });
    else notify("No matching saved note was linked to this task yet.", "coral");
  };
  const openQuiz = (task) => onNavigate?.("quiz", { quizTopic: task.topic, quizNoteId: task.note_id || null });

  return <main className="rp-page rp-simple">
    <header className="rp-header">
      <div><span className="rp-eyebrow">YOUR STUDY PLAN</span><h1>Revision Planner</h1><p>Short, practical revision tasks based on your saved notes and quiz performance.</p></div>
      <div className="rp-header-actions">
        <button className="rp-btn secondary" onClick={() => load()} disabled={loading}>Refresh</button>
        <button className="rp-btn primary" onClick={generatePlan} disabled={busy === "generate"}>{busy === "generate" ? "Updating…" : "Update plan"}</button>
      </div>
    </header>

    {activeSession && <section className="rp-simple-session">
      <div><b>Study session in progress · {activeSession.topic || "Revision"}</b><span>{Math.floor(sessionSeconds / 60)} min {sessionSeconds % 60} sec recorded so far</span></div>
      <button className="rp-btn primary" onClick={finishSession} disabled={busy === "finish"}>{busy === "finish" ? "Saving…" : "Finish session"}</button>
    </section>}

    <div className="rp-simple-summary">
      <span><b>{pending.length}</b> pending</span>
      <span><b>{overdueCount}</b> overdue</span>
      <span><b>{tasks.filter(done).length}</b> completed</span>
    </div>

    {error && <div className="rp-simple-message" role="alert">{error} <button className="rp-btn secondary" onClick={() => load()}>Retry</button></div>}
    {loading ? <p className="rp-simple-muted">Loading your saved plan…</p> : <>
      {nextTask && <section className="rp-panel rp-simple-next">
        <span className="rp-eyebrow">SUGGESTED NEXT</span>
        <h2>{nextTask.title || nextTask.topic}</h2>
        <p>{readableReason(nextTask)}</p>
        <div className="rp-simple-meta">{nextTask.topic} · {durationOf(nextTask)} min · {isOverdue(nextTask) ? "Overdue" : formatDate(nextTask.scheduled_at || nextTask.due_date)}</div>
        <div className="rp-simple-actions">
          <button className="rp-btn primary" onClick={() => startSession(nextTask)} disabled={Boolean(activeSession) || busy === "start-" + nextTask.id}>{activeSession ? "Session active" : "Start study session"}</button>
          <button className="rp-btn secondary" onClick={() => openNote(nextTask)}>Open note</button>
          <button className="rp-btn secondary" onClick={() => openQuiz(nextTask)}>Practice quiz</button>
        </div>
      </section>}

      <section className="rp-panel rp-simple-list-panel">
        <div className="rp-section-heading"><div><h2>Upcoming revisions</h2><p>Saved tasks, updated from the backend.</p></div></div>
        {pending.length ? <div className="rp-simple-list">{pending.map((task) => <article className="rp-simple-task" key={task.id}>
          <div className="rp-simple-task-main"><b>{task.title || task.topic}</b><span>{task.topic} · {durationOf(task)} min</span><small>{task.priority_reason || (task.priority === "high" ? "High priority based on the saved revision plan." : "Scheduled from your learning activity.")}</small><small className={isOverdue(task) ? "rp-simple-overdue" : ""}>{isOverdue(task) ? "Overdue · " : ""}{formatDate(task.scheduled_at || task.due_date)}</small></div>
          <div className="rp-simple-task-actions">
            <button className="rp-btn secondary" onClick={() => { setRescheduleId(rescheduleId === task.id ? null : task.id); setRescheduleAt(localInput(task.scheduled_at || new Date(Date.now() + 86400000))); }}>Reschedule</button>
            <button className="rp-btn secondary" onClick={() => openQuiz(task)}>Quiz</button>
            <button className="rp-btn primary" onClick={() => markDone(task)} disabled={busy === "done-" + task.id}>{busy === "done-" + task.id ? "Saving…" : "Complete"}</button>
          </div>
          {rescheduleId === task.id && <form className="rp-simple-reschedule" onSubmit={(event) => { event.preventDefault(); saveReschedule(task); }}><label>New date and time<input type="datetime-local" value={rescheduleAt} onChange={(event) => setRescheduleAt(event.target.value)} required /></label><button className="rp-btn primary" disabled={busy === "reschedule-" + task.id}>{busy === "reschedule-" + task.id ? "Saving…" : "Save"}</button></form>}
        </article>)}</div> : <p className="rp-simple-muted">No pending revisions. Upload notes or complete a quiz, then update your plan.</p>}
      </section>
    </>}
  </main>;
}
