import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  autoSchedule, cancelPlannerTask, completeStudySession, createPlannerTask, getActiveStudySession,
  getDashboard, getPlanner, getPlannerPreferences, pauseStudySession, resumeStudySession, savePlannerPreferences, startStudySession,
  toggleTask, updatePlannerTask,
} from "../services/api";
import "../styles/revision-planner.css";

const DEFAULT_PREFS = { daily_minutes: 60, planning_days: 14, preferred_start_hour: 18, preferred_end_hour: 22, available_days: [0, 1, 2, 3, 4, 5, 6], topic_importance: {}, deadlines: [] };
const localDay = (date) => {
  const d = new Date(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const parseDate = (value) => {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
};
const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const plusDays = (d, count) => { const next = new Date(d); next.setDate(next.getDate() + count); return next; };
const formatDate = (value, options = { day: "numeric", month: "short" }) => {
  const d = parseDate(value);
  return d ? d.toLocaleDateString(undefined, options) : "Not scheduled";
};
const formatMinutes = (minutes) => {
  const n = Math.max(0, Number(minutes) || 0);
  return n >= 60 ? `${Math.floor(n / 60)}h ${n % 60}m` : `${n} min`;
};
const isDone = (task) => Boolean(task?.done) || task?.status === "completed";
const isCancelled = (task) => task?.status === "cancelled" || task?.status === "skipped";
const getScheduled = (task) => task?.scheduled_at || task?.due_date || null;
const isOverdue = (task, now = new Date()) => {
  if (isDone(task) || isCancelled(task)) return false;
  const date = parseDate(task?.original_due_date || task?.due_date || task?.scheduled_at);
  return Boolean(date && date.getTime() < dayStart(now).getTime());
};
const toInputDateTime = (value) => {
  const d = parseDate(value);
  if (!d) return "";
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

export default function RevisionPlanner({ toast, refreshDashboard, onNavigate }) {
  const [planner, setPlanner] = useState({ tasks: [], deadlines: [], topics: [], summary: {} });
  const [preferences, setPreferences] = useState(DEFAULT_PREFS);
  const [dashboard, setDashboard] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [clockNow, setClockNow] = useState(Date.now());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [view, setView] = useState("week");
  const [anchor, setAnchor] = useState(new Date());
  const [selectedDay, setSelectedDay] = useState(localDay(new Date()));
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftTopic, setDraftTopic] = useState("");
  const [draftMinutes, setDraftMinutes] = useState(25);
  const [draftDate, setDraftDate] = useState(toInputDateTime(new Date(Date.now() + 3600000)));
  const [editDate, setEditDate] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [plan, prefs, dash, sessionResult] = await Promise.all([
        getPlanner(), getPlannerPreferences().catch(() => DEFAULT_PREFS),
        getDashboard().catch(() => null), getActiveStudySession().catch(() => ({ active: null })),
      ]);
      setPlanner({ tasks: [], deadlines: [], topics: [], summary: {}, ...(plan || {}) });
      setPreferences({ ...DEFAULT_PREFS, ...(prefs || plan?.preferences || {}) });
      setDashboard(dash);
      setActiveSession(sessionResult?.active || null);
      const nextTasks = plan?.tasks || [];
      setSelectedTaskId((current) => current && nextTasks.some((t) => String(t.id) === String(current)) ? current : (nextTasks.find((t) => !isDone(t) && !isCancelled(t))?.id ?? nextTasks[0]?.id ?? null));
    } catch (err) {
      setError(err?.message || "Could not load your revision plan.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!activeSession) return undefined;
    const interval = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [activeSession?.session_id, activeSession?.status, activeSession?.active_interval_started_at]);

  const tasks = planner.tasks || [];
  const deadlines = planner.deadlines || preferences.deadlines || [];
  const selectedTask = tasks.find((task) => String(task.id) === String(selectedTaskId)) || null;
  const displayedSessionSeconds = activeSession ? Math.max(0, Number(activeSession.duration_seconds) || 0) + (activeSession.status === "active" && activeSession.active_interval_started_at ? Math.max(0, Math.floor((clockNow - (parseDate(activeSession.active_interval_started_at)?.getTime() || clockNow)) / 1000)) : 0) : 0;
  const period = useMemo(() => {
    if (view === "today") return { start: dayStart(anchor), end: plusDays(dayStart(anchor), 1) };
    if (view === "month") {
      const start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      return { start, end: new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1) };
    }
    const start = dayStart(anchor);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    return { start, end: plusDays(start, 7) };
  }, [anchor, view]);
  const weekDays = useMemo(() => {
    const first = view === "today" ? dayStart(anchor) : view === "month" ? new Date(anchor.getFullYear(), anchor.getMonth(), 1) : (() => {
      const start = dayStart(anchor); start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); return start;
    })();
    const count = view === "today" ? 1 : view === "month" ? new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0).getDate() : 7;
    return Array.from({ length: count }, (_, i) => plusDays(first, i));
  }, [anchor, view]);

  const metricTasks = tasks.filter((task) => {
    const stamp = parseDate(getScheduled(task) || task.completed_at);
    return stamp && stamp >= period.start && stamp < period.end;
  });
  const plannedCount = metricTasks.filter((task) => !isDone(task) && ["planned", "in_progress", "missed"].includes(task.status || "planned")).length;
  const remainingMinutes = metricTasks.filter((task) => !isDone(task) && !isCancelled(task)).reduce((sum, task) => sum + Math.max(0, Number(task.duration_minutes) || parseEstimate(task.est)), 0);
  const completedCount = metricTasks.filter(isDone).length;
  const overdueTasks = tasks.filter((task) => isOverdue(task));
  const studyMinutesToday = Number(dashboard?.analytics?.study_minutes_today) || 0;
  const currentLabel = view === "today" ? formatDate(anchor, { day: "numeric", month: "long", year: "numeric" }) :
    view === "month" ? anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" }) :
      `${formatDate(period.start, { day: "numeric", month: "short" })} – ${formatDate(plusDays(period.end, -1), { day: "numeric", month: "short", year: "numeric" })}`;

  function parseEstimate(value) {
    const text = String(value || "");
    const m = text.match(/(\d+)\s*min/i);
    if (m) return Number(m[1]);
    const h = text.match(/(\d+)\s*h/i);
    return h ? Number(h[1]) * 60 : 20;
  }
  function notify(message, tone = "teal") { toast?.(message, tone); }

  async function generatePlan() {
    setBusy("generate");
    try {
      const result = await autoSchedule();
      await load();
      await refreshDashboard?.();
      if (!(result?.topics_considered > 0)) notify("No eligible topics yet. Upload generated notes or complete a quiz to build a personalized plan.", "coral");
      else notify(`Plan saved · ${result.created_count || 0} created · ${result.rescheduled_count || 0} rescheduled · ${result.retained_count || 0} retained.`);
    } catch (err) { notify(err?.message || "Could not generate the revision plan.", "coral"); }
    finally { setBusy(""); }
  }

  async function completeTask(task) {
    setBusy(`task-${task.id}`);
    try {
      await toggleTask(task.id, !isDone(task));
      await load();
      await refreshDashboard?.();
      notify(isDone(task) ? "Task reopened." : "Revision completed and saved.");
    } catch (err) { notify(err?.message || "Could not update this task.", "coral"); }
    finally { setBusy(""); }
  }

  async function startTask(task) {
    if (!task?.topic) return notify("This task does not have a linked topic.", "coral");
    setBusy(`start-${task.id}`);
    try {
      const result = await startStudySession(task.topic, task.id);
      const session = result?.session || result?.active;
      setActiveSession(session || null);
      if (result?.already_active && session?.topic && session.topic.toLowerCase() !== task.topic.toLowerCase()) {
        notify(`A study session is already active for ${session.topic}. Finish it first.`, "coral");
        return;
      }
      if (!isDone(task)) await updatePlannerTask(task.id, { status: "in_progress" });
      await load();
      notify(`Study session started for ${task.topic}.`);
      if (task.activity_type === "assessment") onNavigate?.("quiz", { quizTopic: task.topic, quizNoteId: task.note_id || null });
      else if (task.note_id) onNavigate?.("notes", { noteId: task.note_id });
    } catch (err) { notify(err?.message || "Could not start a study session.", "coral"); }
    finally { setBusy(""); }
  }

  async function pauseSession() {
    if (!activeSession?.session_id) return;
    setBusy("pause");
    try {
      const result = await pauseStudySession(activeSession.session_id);
      setActiveSession(result?.session || null);
      notify("Study timer paused. Paused time will not be counted.");
    } catch (err) { notify(err?.message || "Could not pause the session.", "coral"); }
    finally { setBusy(""); }
  }

  async function resumeSession() {
    if (!activeSession?.session_id) return;
    setBusy("resume");
    try {
      const result = await resumeStudySession(activeSession.session_id);
      setActiveSession(result?.session || null);
      setClockNow(Date.now());
      notify("Study timer resumed.");
    } catch (err) { notify(err?.message || "Could not resume the session.", "coral"); }
    finally { setBusy(""); }
  }

  async function cancelTask(task) {
    if (!task || !window.confirm("Cancel this revision task? Its study history will be preserved.")) return;
    setBusy("cancel-" + task.id);
    try {
      await cancelPlannerTask(task.id);
      await load();
      await refreshDashboard?.();
      notify("Task cancelled. Its history was preserved.");
    } catch (err) { notify(err?.message || "Could not cancel the task.", "coral"); }
    finally { setBusy(""); }
  }

  async function stopSession() {
    if (!activeSession?.session_id) return;
    setBusy("stop");
    try {
      const result = await completeStudySession(activeSession.session_id);
      setActiveSession(null);
      notify(`Session saved · ${Math.floor((Number(result?.session?.duration_seconds) || 0) / 60)} measured minutes.`);
      await load();
      await refreshDashboard?.();
    } catch (err) { notify(err?.message || "Could not end the session.", "coral"); }
    finally { setBusy(""); }
  }

  async function saveTaskEdit(event) {
    event.preventDefault();
    if (!selectedTask || !editDate) return;
    const when = new Date(editDate);
    if (Number.isNaN(when.getTime())) return notify("Choose a valid date and time.", "coral");
    setBusy("reschedule");
    try {
      await updatePlannerTask(selectedTask.id, { scheduled_at: when.toISOString(), day: localDay(when) === localDay(new Date()) ? "today" : "upcoming", date: when.toLocaleString() });
      setEditDate("");
      await load();
      notify("Revision rescheduled.");
    } catch (err) { notify(err?.message || "Could not reschedule the task.", "coral"); }
    finally { setBusy(""); }
  }

  async function editTask(task) {
    const title = window.prompt("Task title", task.title || "");
    if (title === null) return;
    const cleanTitle = title.trim();
    if (!cleanTitle) return notify("Task title cannot be empty.", "coral");
    const topic = window.prompt("Topic", task.topic || "");
    if (topic === null) return;
    const minutesRaw = window.prompt("Estimated duration in minutes", String(task.duration_minutes || parseEstimate(task.est)));
    if (minutesRaw === null) return;
    const minutes = Number(minutesRaw);
    const priority = window.prompt("Priority: high, med, or low", task.priority || "med");
    if (priority === null) return;
    if (!Number.isInteger(minutes) || minutes < 5 || minutes > 240) return notify("Duration must be between 5 and 240 minutes.", "coral");
    if (!["high", "med", "low"].includes(priority.trim().toLowerCase())) return notify("Priority must be high, med, or low.", "coral");
    setBusy(`edit-${task.id}`);
    try {
      await updatePlannerTask(task.id, { title: cleanTitle, topic: topic.trim() || task.topic, duration_minutes: minutes, est: `${minutes} min`, priority: priority.trim().toLowerCase() });
      await load();
      notify("Revision task updated.");
    } catch (err) { notify(err?.message || "Could not update the task.", "coral"); }
    finally { setBusy(""); }
  }

  async function addTask(event) {
    event.preventDefault();
    if (!draftTitle.trim() || !draftTopic.trim()) return;
    const when = draftDate ? new Date(draftDate) : null;
    if (when && Number.isNaN(when.getTime())) return notify("Choose a valid scheduled date.", "coral");
    setBusy("create");
    try {
      await createPlannerTask({
        title: draftTitle.trim(), topic: draftTopic.trim(), duration_minutes: draftMinutes, est: `${draftMinutes} min`,
        priority: "med", day: when && localDay(when) === localDay(new Date()) ? "today" : "upcoming",
        scheduled_at: when ? when.toISOString() : null, date: when ? when.toLocaleString() : null,
      });
      setDraftTitle(""); setDraftTopic(""); setShowCreate(false);
      await load(); await refreshDashboard?.();
      notify("Revision task saved.");
    } catch (err) { notify(err?.message || "Could not save the task.", "coral"); }
    finally { setBusy(""); }
  }

  async function savePreferences(event) {
    event.preventDefault();
    if (Number(preferences.preferred_end_hour) <= Number(preferences.preferred_start_hour)) return notify("End hour must be later than start hour.", "coral");
    setBusy("preferences");
    try {
      await savePlannerPreferences(preferences);
      await load();
      notify("Study availability saved.");
    } catch (err) { notify(err?.message || "Could not save preferences.", "coral"); }
    finally { setBusy(""); }
  }

  function navigatePeriod(direction) {
    setAnchor((current) => {
      if (view === "today") return plusDays(current, direction);
      if (view === "month") return new Date(current.getFullYear(), current.getMonth() + direction, 1);
      return plusDays(current, direction * 7);
    });
  }

  const taskByDay = useMemo(() => {
    const map = new Map();
    tasks.forEach((task) => {
      const stamp = parseDate(getScheduled(task));
      if (!stamp) {
        if (task.day === "today") {
          const key = localDay(new Date());
          map.set(key, [...(map.get(key) || []), task]);
        }
        return;
      }
      const key = localDay(stamp);
      map.set(key, [...(map.get(key) || []), task]);
    });
    return map;
  }, [tasks]);

  const daysWithTasks = weekDays.map((day) => ({ date: day, key: localDay(day), tasks: (taskByDay.get(localDay(day)) || []).slice().sort((a, b) => (a.priority === "high" ? -1 : 0) - (b.priority === "high" ? -1 : 0)) }));
  const topics = planner.topics || [];
  const recommended = tasks.filter((task) => !isDone(task) && !isCancelled(task)).sort((a, b) => {
    if (isOverdue(a) !== isOverdue(b)) return isOverdue(a) ? -1 : 1;
    const p = { high: 0, med: 1, low: 2 };
    return (p[a.priority] ?? 3) - (p[b.priority] ?? 3) || (parseDate(getScheduled(a))?.getTime() ?? Infinity) - (parseDate(getScheduled(b))?.getTime() ?? Infinity);
  }).slice(0, 8);

  return (
    <main className="rp-page">
      <header className="rp-header">
        <div><div className="rp-eyebrow">STUDY WITH INTENTION</div><h1>Revision <em>Planner</em></h1><p>Your personalized study schedule, built from your saved learning activity.</p></div>
        <div className="rp-header-actions"><span className="rp-date-chip">{new Date().toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</span><button className="rp-btn secondary" onClick={() => { setShowCreate((v) => !v); setDraftDate(toInputDateTime(new Date(Date.now() + 3600000))); }}>＋ Add task</button><button className="rp-btn primary" disabled={busy === "generate"} onClick={generatePlan}>{busy === "generate" ? "Building plan…" : "✦ Generate / Update Plan"}</button></div>
      </header>

      {activeSession && <section className="rp-session-banner"><span className="rp-live-dot"/><div><b>Study session active{activeSession.topic ? ` · ${activeSession.topic}` : ""}</b><small>{activeSession.status === "paused" ? "Paused" : "Timer running"} · {formatMinutes(Math.floor(displayedSessionSeconds / 60))} measured so far · paused time is excluded.</small></div>{activeSession.status === "paused" ? <button className="rp-btn secondary" disabled={busy === "resume"} onClick={resumeSession}>{busy === "resume" ? "Resuming…" : "Resume"}</button> : <button className="rp-btn secondary" disabled={busy === "pause"} onClick={pauseSession}>{busy === "pause" ? "Pausing…" : "Pause"}</button>}<button className="rp-btn primary" disabled={busy === "stop"} onClick={stopSession}>{busy === "stop" ? "Saving…" : "Finish session"}</button></section>}

      <section className="rp-metrics">
        <Metric label="Planned sessions" value={plannedCount} helper={currentLabel} glyph="▦"/>
        <Metric label="Planned study time" value={formatMinutes(remainingMinutes)} helper="Remaining estimates, not actual time" glyph="◷"/>
        <Metric label="Completed sessions" value={completedCount} helper={`In ${view === "today" ? "this day" : view === "month" ? "this month" : "this week"}`} glyph="✓"/>
        <Metric label="Overdue tasks" value={overdueTasks.length} helper="Incomplete and past due" glyph="!"/>
        <Metric label="Actual study time today" value={formatMinutes(studyMinutesToday)} helper="Measured from saved study sessions" glyph="◴"/>
      </section>

      {error && <div className="rp-error" role="alert">{error} <button className="rp-btn secondary" onClick={load}>Retry</button></div>}
      {loading ? <div className="rp-empty"><div className="rp-spinner"/>Loading your saved planner data…</div> : <>
        {showCreate && <form className="rp-create-form" onSubmit={addTask}>
          <label>Task title<input required maxLength={200} value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)} placeholder="Review a concept"/></label>
          <label>Topic<input required maxLength={120} value={draftTopic} onChange={(e) => setDraftTopic(e.target.value)} placeholder="Topic or note title"/></label>
          <label>Duration<select value={draftMinutes} onChange={(e) => setDraftMinutes(Number(e.target.value))}>{[15,20,25,30,45,60,90].map((n) => <option key={n} value={n}>{n} minutes</option>)}</select></label>
          <label>Schedule<input type="datetime-local" value={draftDate} onChange={(e) => setDraftDate(e.target.value)}/></label>
          <button className="rp-btn primary" disabled={busy === "create"}>{busy === "create" ? "Saving…" : "Save task"}</button>
        </form>}

        <section className="rp-calendar-panel">
          <div className="rp-section-heading"><div><h2>Study calendar</h2><p>Select a date to see its sessions and open a task's details.</p></div><div className="rp-calendar-controls"><button className="rp-btn secondary" onClick={() => setAnchor(new Date())}>Today</button><div className="rp-view-tabs">{[["today","Today"],["week","Week"],["month","Month"]].map(([value,label]) => <button key={value} className={view === value ? "active" : ""} aria-pressed={view === value} onClick={() => { setView(value); setSelectedDay(localDay(new Date())); }}>{label}</button>)}</div></div></div>
          <div className="rp-period-nav"><button aria-label="Previous period" onClick={() => navigatePeriod(-1)}>‹</button><b>{currentLabel}</b><button aria-label="Next period" onClick={() => navigatePeriod(1)}>›</button></div>
          <div className={`rp-calendar-grid ${view === "month" ? "month" : view === "today" ? "one-day" : ""}`}>
            {view !== "month" && daysWithTasks.map(({date,key, tasks: dayTasks}) => <button key={key} className={`rp-day ${selectedDay === key ? "selected" : ""} ${localDay(date) === localDay(new Date()) ? "is-today" : ""}`} onClick={() => setSelectedDay(key)} aria-pressed={selectedDay === key}><span>{date.toLocaleDateString(undefined,{weekday:"short"})}</span><b>{date.getDate()}</b><small>{dayTasks.length ? `${dayTasks.length} session${dayTasks.length === 1 ? "" : "s"}` : "No sessions"}</small><span className="rp-day-dots">{dayTasks.slice(0,4).map((task) => <i key={task.id} className={isDone(task) ? "done" : isOverdue(task) ? "overdue" : task.priority || "med"}/>)}</span></button>)}
            {view === "month" && weekDays.map(({date,key, tasks: dayTasks}) => <button key={key} className={`rp-month-day ${selectedDay === key ? "selected" : ""} ${localDay(date) === localDay(new Date()) ? "is-today" : ""}`} onClick={() => setSelectedDay(key)} aria-pressed={selectedDay === key}><b>{date.getDate()}</b>{dayTasks.slice(0,2).map((task) => <span key={task.id} className={`rp-month-task ${isDone(task) ? "done" : isOverdue(task) ? "overdue" : task.priority || "med"}`}>{task.title}</span>)}{dayTasks.length > 2 && <small>+{dayTasks.length - 2} more</small>}</button>)}
          </div>
          <div className="rp-selected-day"><div className="rp-section-heading"><div><h2>{formatDate(selectedDay + "T12:00:00", { weekday: "long", day: "numeric", month: "long" })}</h2><p>{(taskByDay.get(selectedDay) || []).length} saved revision task(s)</p></div><button className="rp-btn secondary" onClick={() => { setDraftDate(selectedDay + "T18:00"); setShowCreate(true); }}>＋ Add to this day</button></div>
            {(taskByDay.get(selectedDay) || []).length ? <div className="rp-day-task-list">{(taskByDay.get(selectedDay) || []).map((task) => <TaskCard key={task.id} task={task} selected={String(task.id) === String(selectedTaskId)} onSelect={() => setSelectedTaskId(task.id)}/>)}</div> : <div className="rp-empty-inline"><b>No revision sessions scheduled for this date</b><span>Generate a plan or add a task for this day.</span></div>}
          </div>
        </section>

        <div className="rp-workspace-grid">
          <section className="rp-panel">
            <div className="rp-section-heading"><div><h2>What to study next</h2><p>Overdue and high-priority work appears first, using saved evidence.</p></div><span className="rp-count">{recommended.length} pending</span></div>
            {recommended.length ? <div className="rp-recommendations">{recommended.map((task) => <TaskCard key={task.id} task={task} selected={String(task.id) === String(selectedTaskId)} onSelect={() => { setSelectedTaskId(task.id); const d = parseDate(getScheduled(task)); if (d) setSelectedDay(localDay(d)); }}/>)}</div> : <div className="rp-empty-inline"><b>No pending revisions</b><span>There are no unfinished saved tasks. Generate a plan from your notes and quiz history, or add a task.</span></div>}
          </section>

          <aside className="rp-panel rp-detail">
            <div className="rp-section-heading"><div><h2>Task details</h2><p>Evidence, session controls and schedule edits.</p></div></div>
            {selectedTask ? <>
              <div className="rp-detail-kicker"><span className={`rp-status-dot ${isDone(selectedTask) ? "done" : isOverdue(selectedTask) ? "overdue" : ""}`}/>{isDone(selectedTask) ? "Completed" : isOverdue(selectedTask) ? "Overdue" : selectedTask.status === "in_progress" ? "In progress" : "Scheduled"}</div>
              <h3>{selectedTask.title}</h3><p className="rp-topic">{selectedTask.topic}</p>
              <p className="rp-reason">{selectedTask.priority_reason || (selectedTask.evidence?.mastery == null ? "Not enough performance data yet. This task is based on the available note/activity record." : "Recommended from topic performance and scheduling rules.")}</p>
              <div className="rp-detail-facts">
                <div><small>Priority</small><b className={`rp-priority ${selectedTask.priority || "med"}`}>{String(selectedTask.priority || "scheduled").toUpperCase()}</b></div>
                <div><small>Estimated duration</small><b>{formatMinutes(Number(selectedTask.duration_minutes) || parseEstimate(selectedTask.est))}</b></div>
                <div><small>Scheduled</small><b>{formatDateTimeSafe(selectedTask.scheduled_at || selectedTask.date)}</b></div>
                <div><small>Original deadline</small><b>{formatDateTimeSafe(selectedTask.original_due_date || selectedTask.due_date)}</b></div>
                <div><small>Topic mastery</small><b>{selectedTask.evidence?.mastery == null ? "Not assessed" : Math.round(Number(selectedTask.evidence.mastery) * 100) + "%"}</b></div>
                <div><small>Recent trend</small><b>{selectedTask.evidence?.trend || "Insufficient data"}</b></div>
              </div>
              {selectedTask.note_id && <button className="rp-link" onClick={() => onNavigate?.("notes", { noteId: selectedTask.note_id })}>Open linked study notes ↗</button>}
              <div className="rp-actions">
                {!isDone(selectedTask) && <button className="rp-btn primary" disabled={busy === `start-${selectedTask.id}`} onClick={() => startTask(selectedTask)}>{busy === `start-${selectedTask.id}` ? "Starting…" : "▶ Start session"}</button>}
                {!isDone(selectedTask) && <button className="rp-btn secondary" disabled={busy === `task-${selectedTask.id}`} onClick={() => completeTask(selectedTask)}>✓ Mark complete</button>}
                <button className="rp-btn secondary" disabled={busy === `edit-${selectedTask.id}`} onClick={() => editTask(selectedTask)}>Edit task</button>
                {!isDone(selectedTask) && !isCancelled(selectedTask) && <button className="rp-btn secondary" onClick={() => setEditDate((current) => current ? "" : toInputDateTime(getScheduled(selectedTask) || new Date()))}>Reschedule</button>}
                {!isDone(selectedTask) && !isCancelled(selectedTask) && <button className="rp-btn secondary" disabled={busy === "cancel-" + selectedTask.id} onClick={() => cancelTask(selectedTask)}>{busy === "cancel-" + selectedTask.id ? "Cancelling…" : "Cancel task"}</button>}
                {editDate && <form className="rp-reschedule" onSubmit={saveTaskEdit}><label>New date and time<input type="datetime-local" value={editDate} onChange={(e) => setEditDate(e.target.value)} required/></label><button className="rp-btn primary" disabled={busy === "reschedule"}>{busy === "reschedule" ? "Saving…" : "Save schedule"}</button></form>}
              </div>
            </> : <div className="rp-empty-inline"><b>Select a revision task</b><span>Task details will appear here once you select a saved task.</span></div>}
          </aside>
        </div>

        <section className="rp-panel rp-settings">
          <div className="rp-section-heading"><div><h2>Study availability & deadlines</h2><p>Scheduling defaults are preferences, not invented learner history.</p></div><button className="rp-btn secondary" onClick={() => setShowSettings((v) => !v)}>{showSettings ? "Hide settings" : "Configure"}</button></div>
          {showSettings && <form className="rp-settings-form" onSubmit={savePreferences}>
            <label>Daily study budget (minutes)<input type="number" min="15" max="600" value={preferences.daily_minutes} onChange={(e) => setPreferences((v) => ({ ...v, daily_minutes: Number(e.target.value) }))} required/></label>
            <label>Plan ahead (days)<input type="number" min="1" max="60" value={preferences.planning_days} onChange={(e) => setPreferences((v) => ({ ...v, planning_days: Number(e.target.value) }))} required/></label>
            <label>Available from (hour)<input type="number" min="0" max="23" value={preferences.preferred_start_hour} onChange={(e) => setPreferences((v) => ({ ...v, preferred_start_hour: Number(e.target.value) }))} required/></label>
            <label>Available until (hour)<input type="number" min="1" max="24" value={preferences.preferred_end_hour} onChange={(e) => setPreferences((v) => ({ ...v, preferred_end_hour: Number(e.target.value) }))} required/></label>
            <div className="rp-available-days"><b>Available study days</b><div>{[["Mon",0],["Tue",1],["Wed",2],["Thu",3],["Fri",4],["Sat",5],["Sun",6]].map(([label,day]) => <label key={day}><input type="checkbox" checked={(preferences.available_days || [0,1,2,3,4,5,6]).includes(day)} onChange={(event) => setPreferences((v) => ({ ...v, available_days: event.target.checked ? [...new Set([...(v.available_days || [0,1,2,3,4,5,6]), day])].sort() : (v.available_days || [0,1,2,3,4,5,6]).filter((item) => item !== day) }))}/>{label}</label>)}</div></div>
            <div className="rp-deadlines"><b>User-provided deadlines</b>{deadlines.map((deadline, index) => <div className="rp-deadline-row" key={deadline.topic + deadline.date + index}><span>{deadline.text || deadline.topic}<small>{deadline.topic} · {formatDate(deadline.date, { day: "numeric", month: "short", year: "numeric" })}</small></span><button type="button" className="rp-btn secondary" onClick={() => { const next = [...deadlines]; next.splice(index, 1); setPreferences((v) => ({ ...v, deadlines: next })); }}>Remove</button></div>)}<DeadlineAdder onAdd={(item) => setPreferences((v) => ({ ...v, deadlines: [...(v.deadlines || []), item] }))}/></div>
            <button className="rp-btn primary" disabled={busy === "preferences"}>{busy === "preferences" ? "Saving…" : "Save preferences"}</button>
          </form>}
        </section>
      </>}
    </main>
  );
}

function TaskCard({ task, selected, onSelect }) {
  const overdue = isOverdue(task);
  const done = isDone(task);
  const status = done ? "Completed" : isCancelled(task) ? "Cancelled" : overdue ? "Overdue" : task.status === "in_progress" ? "In progress" : task.priority === "high" ? "High priority" : "Scheduled";
  return <button type="button" className={`rp-task-card ${selected ? "selected" : ""} ${done ? "completed" : ""} ${overdue ? "overdue" : ""}`} onClick={onSelect}>
    <span className="rp-task-leading">{done ? "✓" : overdue ? "!" : task.priority === "high" ? "↑" : "↻"}</span>
    <span className="rp-task-content"><b>{task.title || task.topic}</b><span>{task.topic || "Topic not linked"} · {formatMinutes(Number(task.duration_minutes) || parseEstimate(task.est))}</span><small>{task.priority_reason || "No additional performance evidence is available yet."}</small></span>
    <span className={`rp-task-status ${done ? "done" : overdue ? "overdue" : task.priority || "med"}`}>{status}</span>
    <span className="rp-task-date">{formatDate(getScheduled(task))}</span>
  </button>;
}

function Metric({ label, value, helper, glyph }) {
  return <article className="rp-metric"><span className="rp-metric-icon">{glyph}</span><small>{label}</small><strong>{value}</strong><span>{helper}</span></article>;
}
function DeadlineAdder({ onAdd }) {
  const [topic, setTopic] = useState(""); const [date, setDate] = useState(""); const [label, setLabel] = useState("");
  function submit(event) {
    event.preventDefault();
    if (!topic.trim() || !date) return;
    onAdd({ topic: topic.trim(), date, text: label.trim() || `Deadline: ${topic.trim()}` });
    setTopic(""); setDate(""); setLabel("");
  }
  return <form className="rp-deadline-adder" onSubmit={submit}><input aria-label="Deadline topic" placeholder="Topic" value={topic} onChange={(e) => setTopic(e.target.value)} required/><input aria-label="Deadline date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required/><input aria-label="Deadline label" placeholder="Exam / assignment (optional)" value={label} onChange={(e) => setLabel(e.target.value)}/><button className="rp-btn secondary">Add deadline</button></form>;
}
function formatDateTimeSafe(value) {
  const date = parseDate(value);
  return date ? date.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "Not set";
}
