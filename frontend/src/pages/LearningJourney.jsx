import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  autoSchedule, completeStudySession, createPlannerTask, getActiveStudySession,
  getPlanner, getPlannerPreferences, savePlannerPreferences, startStudySession,
  toggleTask, updatePlannerTask,
} from "../services/api";
import "../styles/learning-journey.css";

const DEFAULT_PREFS = { daily_minutes: 60, planning_days: 7, preferred_start_hour: 18, preferred_end_hour: 22, topic_importance: {}, deadlines: [] };
const TYPE_LABELS = {
  quiz_completed: "Quiz completed", note_view: "Note reviewed", deadline: "Upcoming deadline",
  study_session_completed: "Study session", planner_task_done: "Revision completed",
  planner_task_edited: "Task updated", revision: "Revision task",
};
const parseDate = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};
const formatDate = (value, options = { day: "numeric", month: "short" }) => {
  const parsed = parseDate(value);
  return parsed ? parsed.toLocaleDateString(undefined, options) : "Date not set";
};
const formatDateTime = (value) => {
  const parsed = parseDate(value);
  return parsed ? parsed.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "Not scheduled";
};
const topicSlug = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const eventLabel = (event) => TYPE_LABELS[event.type] || String(event.type || "Learning event").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const isCompleted = (task) => Boolean(task?.done) || task?.status === "completed";
const eventIsOverdue = (event, tasks) => {
  const task = tasks.find((item) => String(item.id) === String(event.task_id || "").replace(/^task-/, ""));
  if (!task || isCompleted(task)) return false;
  const when = parseDate(task.due_date || task.original_due_date || task.scheduled_at);
  return Boolean(when && when.getTime() < Date.now());
};
function periodBounds(anchor, range) {
  const start = new Date(anchor);
  start.setHours(0, 0, 0, 0);
  if (range === "day") return { start, end: new Date(start.getTime() + 86400000 - 1) };
  if (range === "week") {
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    const end = new Date(start);
    end.setDate(end.getDate() + 7);
    end.setMilliseconds(-1);
    return { start, end };
  }
  if (range === "month") {
    start.setDate(1);
    const end = new Date(start.getFullYear(), start.getMonth() + 1, 1);
    end.setMilliseconds(-1);
    return { start, end };
  }
  return { start: null, end: null };
}
function changeAnchor(anchor, range, amount) {
  const next = new Date(anchor);
  if (range === "day") next.setDate(next.getDate() + amount);
  else if (range === "month") next.setMonth(next.getMonth() + amount);
  else next.setDate(next.getDate() + amount * 7);
  return next;
}
function masteryState(topic) {
  if (topic?.mastery_pct == null) return { label: "Not assessed", className: "unknown" };
  if (topic.mastery_pct < 40) return { label: "Critical", className: "critical" };
  if (topic.mastery_pct < 70 || topic.trend_label === "declining") return { label: "Needs practice", className: "practice" };
  if (topic.mastery_pct >= 85 && (topic.attempts || 0) >= 2) return { label: "Strong", className: "strong" };
  if (topic.trend_label === "improving") return { label: "Improving", className: "improving" };
  return { label: "Developing", className: "practice" };
}
function Icon({ name }) {
  const paths = {
    spark: <><path d="m12 3 2.2 5.5L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.5z"/><path d="m19 3 .8 2.2L22 6l-2.2.8L19 9l-.8-2.2L16 6l2.2-.8z"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/></>,
    quiz: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="m8 12 2.5 2.5L16 9"/></>,
    notes: <><path d="M6 3h9l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM14 3v5h5M8 12h8M8 16h6"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/></>,
    target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="m12 12 7-7"/></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
  };
  return <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.spark}</svg>;
}

export default function LearningJourney({ onNavigate, toast, refreshDashboard }) {
  const [planner, setPlanner] = useState(null);
  const [preferences, setPreferences] = useState(DEFAULT_PREFS);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [range, setRange] = useState("week");
  const [anchor, setAnchor] = useState(new Date());
  const [topicFilter, setTopicFilter] = useState("all");
  const [eventFilter, setEventFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedId, setSelectedId] = useState(null);
  const [showPreferences, setShowPreferences] = useState(false);
  const [deadlineTopic, setDeadlineTopic] = useState("");
  const [deadlineDate, setDeadlineDate] = useState("");
  const [deadlineText, setDeadlineText] = useState("");
  const [deadlineEditIndex, setDeadlineEditIndex] = useState(null);
  const [rescheduleAt, setRescheduleAt] = useState("");
  const [showCreateTask, setShowCreateTask] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newTopic, setNewTopic] = useState("");
  const [newMinutes, setNewMinutes] = useState(20);
  const [activeSession, setActiveSession] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [plannerData, prefData, activeData] = await Promise.all([
        getPlanner(), getPlannerPreferences().catch(() => DEFAULT_PREFS), getActiveStudySession().catch(() => ({ active: null })),
      ]);
      setPlanner(plannerData || { tasks: [], events: [], topics: [], summary: {} });
      setPreferences({ ...DEFAULT_PREFS, ...(prefData || plannerData?.preferences || {}) });
      setActiveSession(activeData?.active || null);
      const first = (plannerData?.events || []).find((event) => event.id);
      setSelectedId((current) => current || first?.id || null);
    } catch (err) {
      setError(err?.message || "Could not load your learning journey.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const tasks = planner?.tasks || [];
  const topics = planner?.topics || [];
  const events = planner?.events || [];
  const summary = planner?.summary || {};
  const bounds = useMemo(() => periodBounds(anchor, range), [anchor, range]);
  const topicNames = useMemo(() => [...new Set([
    ...topics.map((topic) => topic.topic).filter(Boolean),
    ...tasks.map((task) => task.topic).filter(Boolean),
    ...events.map((event) => event.topic).filter(Boolean),
  ])].sort((a, b) => a.localeCompare(b)), [topics, tasks, events]);

  const visibleEvents = useMemo(() => events.filter((event) => {
    const stamp = parseDate(event.timestamp);
    if (range !== "all") {
      if (!stamp) return event.source === "planner";
      if (bounds.start && stamp < bounds.start) return false;
      if (bounds.end && stamp > bounds.end) return false;
    }
    if (topicFilter !== "all" && String(event.topic || "").toLowerCase() !== topicFilter.toLowerCase()) return false;
    if (eventFilter === "revision" && event.source !== "planner") return false;
    if (eventFilter === "quizzes" && event.type !== "quiz_completed") return false;
    if (eventFilter === "notes" && event.type !== "note_view") return false;
    if (eventFilter === "completed" && !String(event.status).includes("completed")) return false;
    if (eventFilter === "overdue" && !eventIsOverdue(event, tasks)) return false;
    if (eventFilter === "weak" && !topics.some((topic) => String(topic.topic || "").toLowerCase() === String(event.topic || "").toLowerCase() && ((topic.mastery_pct ?? 100) < 70 || topic.trend_label === "declining"))) return false;
    if (statusFilter === "planned" && (!["planner", "deadline"].includes(event.source) || String(event.status).includes("completed"))) return false;
    if (statusFilter === "completed" && !String(event.status).includes("completed")) return false;
    if (statusFilter === "overdue" && !eventIsOverdue(event, tasks)) return false;
    return true;
  }).sort((a, b) => {
    const da = parseDate(a.timestamp)?.getTime() ?? Number.MAX_SAFE_INTEGER;
    const db = parseDate(b.timestamp)?.getTime() ?? Number.MAX_SAFE_INTEGER;
    return da - db;
  }), [events, range, bounds, topicFilter, eventFilter, statusFilter, tasks, topics]);

  const selected = visibleEvents.find((event) => String(event.id) === String(selectedId)) || visibleEvents[0] || null;
  const selectedTask = selected?.task_id != null ? tasks.find((task) => String(task.id) === String(selected.task_id)) : null;

  async function handleGenerate() {
    setBusy("generate");
    try {
      const result = await autoSchedule();
      await load();
      await refreshDashboard?.();
      if (!result.topics_considered) toast?.("No topic-specific quiz evidence yet. Complete a quiz to generate a personalized revision schedule.", "coral");
      else toast?.("Schedule saved · " + result.created_count + " created · " + result.rescheduled_count + " rescheduled · " + result.retained_count + " retained.", "teal");
    } catch (err) {
      toast?.(err?.message || "Revision plan generation failed.", "coral");
    } finally { setBusy(""); }
  }

  async function markComplete(task) {
    setBusy("task-" + task.id);
    try {
      await toggleTask(task.id, true);
      toast?.("Revision completed and saved.", "teal");
      await load();
      await refreshDashboard?.();
    } catch (err) {
      toast?.(err?.message || "Could not complete this task.", "coral");
    } finally { setBusy(""); }
  }

  async function startRevision(event) {
    const topic = event?.topic || selectedTask?.topic || "";
    if (!topic) {
      toast?.("This activity has no topic linked to it yet.", "coral");
      return;
    }
    setBusy("start");
    try {
      const result = await startStudySession(topic);
      const session = result?.session || result?.active || null;
      setActiveSession(session);
      if (result?.already_active && session?.topic && session.topic.toLowerCase() !== topic.toLowerCase()) {
        toast?.("A study session is already active for " + session.topic + ". Finish it before starting another topic.", "coral");
        return;
      }
      if (selectedTask) {
        try {
          await updatePlannerTask(selectedTask.id, { status: "in_progress" });
          await load();
        } catch (statusError) {
          toast?.("Study session started, but the task status could not be updated: " + (statusError?.message || "please retry."), "coral");
        }
      }
      toast?.("Study session started for " + topic + ". End the session here when you finish to record measured time.", "teal");
      const noteId = selectedTask?.note_id || selectedTask?.linked_note_id;
      if (noteId) onNavigate?.("notes", { noteId });
    } catch (err) {
      toast?.(err?.message || "Could not start a study session.", "coral");
    } finally { setBusy(""); }
  }

  async function stopSession() {
    if (!activeSession?.session_id) return;
    setBusy("stop");
    try {
      const result = await completeStudySession(activeSession.session_id);
      setActiveSession(null);
      const seconds = Number(result?.session?.duration_seconds) || 0;
      toast?.("Study session saved · " + Math.floor(seconds / 60) + " measured minutes.", "teal");
      await load();
      await refreshDashboard?.();
    } catch (err) {
      toast?.(err?.message || "Could not end this study session.", "coral");
    } finally { setBusy(""); }
  }

  async function saveReschedule() {
    if (!selectedTask || !rescheduleAt) return;
    const localDate = new Date(rescheduleAt);
    if (Number.isNaN(localDate.getTime())) {
      toast?.("Choose a valid date and time.", "coral");
      return;
    }
    setBusy("reschedule");
    try {
      await updatePlannerTask(selectedTask.id, { scheduled_at: localDate.toISOString(), date: localDate.toLocaleString(), day: localDate.toDateString() === new Date().toDateString() ? "today" : "upcoming" });
      toast?.("Task rescheduled. Its original deadline is preserved.", "teal");
      setRescheduleAt("");
      await load();
      await refreshDashboard?.();
    } catch (err) {
      toast?.(err?.message || "Could not reschedule this task.", "coral");
    } finally { setBusy(""); }
  }

  async function savePrefs(event) {
    event.preventDefault();
    setBusy("preferences");
    try {
      const result = await savePlannerPreferences(preferences);
      setPreferences({ ...DEFAULT_PREFS, ...(result.preferences || preferences) });
      toast?.("Scheduling preferences saved.", "teal");
      await load();
    } catch (err) {
      toast?.(err?.message || "Could not save scheduling preferences.", "coral");
    } finally { setBusy(""); }
  }

  async function addDeadline(event) {
    event.preventDefault();
    if (!deadlineTopic.trim() || !deadlineDate) {
      toast?.("Enter the topic and deadline date.", "coral");
      return;
    }
    const deadlines = [...(preferences.deadlines || [])];
    const item = { topic: deadlineTopic.trim(), text: deadlineText.trim() || deadlineTopic.trim(), date: new Date(deadlineDate + "T23:59:00").toISOString() };
    if (deadlineEditIndex == null) deadlines.push(item);
    else deadlines[deadlineEditIndex] = item;
    const next = { ...preferences, deadlines };
    setBusy("deadline");
    try {
      const result = await savePlannerPreferences(next);
      setPreferences({ ...DEFAULT_PREFS, ...(result.preferences || next) });
      setDeadlineTopic(""); setDeadlineDate(""); setDeadlineText(""); setDeadlineEditIndex(null);
      toast?.(deadlineEditIndex == null ? "Deadline saved. Generate the plan again to apply it." : "Deadline updated. Generate the plan again to apply it.", "teal");
    } catch (err) {
      toast?.(err?.message || "Could not save this deadline.", "coral");
    } finally { setBusy(""); }
  }

  async function removeDeadline(index) {
    const next = { ...preferences, deadlines: (preferences.deadlines || []).filter((_, i) => i !== index) };
    setBusy("deadline");
    try {
      const result = await savePlannerPreferences(next);
      setPreferences({ ...DEFAULT_PREFS, ...(result.preferences || next) });
      toast?.("Deadline removed.", "teal");
    } catch (err) {
      toast?.(err?.message || "Could not remove deadline.", "coral");
    } finally { setBusy(""); }
  }

  async function addManualTask(event) {
    event.preventDefault();
    if (!newTitle.trim() || !newTopic.trim()) {
      toast?.("Enter a task title and topic.", "coral");
      return;
    }
    setBusy("create");
    try {
      const result = await createPlannerTask({ title: newTitle.trim(), topic: newTopic.trim(), duration_minutes: Number(newMinutes), est: Number(newMinutes) + " min", priority: "med", day: "upcoming" });
      setNewTitle(""); setNewTopic(""); setShowCreateTask(false);
      toast?.("Revision task saved.", "teal");
      await load();
      setSelectedId("task-" + result.task.id);
      await refreshDashboard?.();
    } catch (err) {
      toast?.(err?.message || "Could not create task.", "coral");
    } finally { setBusy(""); }
  }

  const headingDate = range === "all" ? "All learning activity" : range === "month" ? anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" }) : range === "day" ? formatDate(anchor.toISOString(), { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : "Week of " + formatDate(bounds.start?.toISOString(), { day: "numeric", month: "short" });
  const completedCount = tasks.filter(isCompleted).length;

  if (loading && !planner) return <div className="lj-page"><div className="lj-loading"><span className="lj-spinner"/>Loading your learning journey…</div></div>;
  if (error && !planner) return <div className="lj-page"><div className="lj-error"><b>Your learning journey is unavailable</b><p>{error}</p><button className="lj-btn primary" onClick={load}>Retry</button><button className="lj-btn" onClick={() => onNavigate?.("dashboard")}>Back to dashboard</button></div></div>;

  return <main className="lj-page">
    <header className="lj-page-header">
      <div>
        <div className="lj-breadcrumb"><button onClick={() => onNavigate?.("dashboard")}>Dashboard</button><span>/</span><b>Learning Journey</b></div>
        <div className="lj-overline">YOUR PERSONALIZED LEARNING PATH</div>
        <h1>Your Learning <em>Journey</em></h1>
        <p>See how your learning activity connects to what you should focus on next.</p>
      </div>
      <div className="lj-header-actions">
        <button className="lj-btn" onClick={() => onNavigate?.("dashboard")}>← Dashboard</button>
        <button className="lj-btn" onClick={() => onNavigate?.("planner")}>Open Revision Planner <Icon name="arrow"/></button>
        <button className="lj-btn primary" disabled={busy === "generate"} onClick={handleGenerate}>{busy === "generate" ? <><span className="lj-spinner small"/> Generating…</> : <><Icon name="spark"/> Generate Revision Plan</>}</button>
      </div>
    </header>

    {activeSession && <section className="lj-session-banner"><span className="lj-live-dot"/><div><b>Study session in progress</b><small>{activeSession.topic || "General study"} · time is measured by the server</small></div><button className="lj-btn primary" disabled={busy === "stop"} onClick={stopSession}>{busy === "stop" ? "Saving…" : "End session"}</button></section>}

    <section className="lj-stat-grid" aria-label="Learning overview">
      {[
        { icon: "target", label: "Topics tracked", value: summary.topics_tracked ?? topics.length, note: "From saved quiz attempts", filter: "all" },
        { icon: "spark", label: "Need revision", value: summary.topics_needing_revision ?? topics.filter((topic) => topic.mastery_pct != null && topic.mastery_pct < 70).length, note: "Evidence-backed focus areas", filter: "weak" },
        { icon: "calendar", label: "Upcoming sessions", value: summary.upcoming_sessions ?? tasks.filter((task) => !isCompleted(task)).length, note: "Saved planner tasks", filter: "revision" },
        { icon: "clock", label: "Overdue tasks", value: summary.overdue_tasks ?? 0, note: "Incomplete past-due work", filter: "overdue" },
        { icon: "quiz", label: "Milestones completed", value: summary.completed_milestones ?? completedCount, note: "Persisted completed tasks", filter: "completed" },
      ].map((card) => <button type="button" className="lj-stat-card" key={card.label} onClick={() => { setEventFilter(card.filter === "all" ? "all" : card.filter); setStatusFilter("all"); }}>
        <span className="lj-stat-icon"><Icon name={card.icon}/></span><small>{card.label}</small><strong>{card.value}</strong><span>{card.note}</span>
      </button>)}
    </section>

    <section className="lj-panel lj-topic-panel">
      <div className="lj-section-heading"><div><span className="lj-section-icon"><Icon name="target"/></span><div><h2>Topic mastery</h2><p>Measured from your saved quiz results, not note uploads.</p></div></div><span className="lj-count">{topics.length} topic{topics.length === 1 ? "" : "s"}</span></div>
      {topics.length ? <div className="lj-topic-strip">{topics.map((topic) => {
        const state = masteryState(topic);
        return <button key={topic.topic} className={"lj-topic-card " + state.className + (topicFilter === topic.topic ? " selected" : "")} onClick={() => setTopicFilter(topicFilter === topic.topic ? "all" : topic.topic)}>
          <span className="lj-topic-top"><b>{topic.topic}</b><span className={"lj-state " + state.className}>{state.label}</span></span>
          {topic.mastery_pct == null ? <div className="lj-topic-unknown">Not enough assessment evidence</div> : <><div className="lj-topic-score">{Math.round(topic.mastery_pct)}<small>%</small></div><div className="lj-track"><i style={{ width: Math.max(0, Math.min(100, topic.mastery_pct)) + "%" }}/></div></>}
          <div className="lj-topic-meta"><span>{topic.attempts || 0} attempt{topic.attempts === 1 ? "" : "s"}</span><span>{topic.last_reviewed_at ? "Assessed " + formatDate(topic.last_reviewed_at) : "No assessment date"}</span></div>
          <div className="lj-topic-foot">{topic.trend_label === "improving" ? "↗ Improving" : topic.trend_label === "declining" ? "↘ Declining" : topic.trend_label === "stable" ? "→ Stable" : "Evidence limited"}</div>
        </button>;
      })}</div> : <div className="lj-empty-inline"><Icon name="quiz"/><div><b>No topics assessed yet</b><p>Complete a quiz to establish topic-level performance. The timeline will not invent mastery scores.</p></div><button className="lj-btn" onClick={() => onNavigate?.("quiz")}>Practice a quiz <Icon name="arrow"/></button></div>}
    </section>

    <section className="lj-panel lj-timeline-panel">
      <div className="lj-section-heading"><div><span className="lj-section-icon"><Icon name="calendar"/></span><div><h2>Learning timeline</h2><p>Past activity and future tasks in one connected view.</p></div></div><button className="lj-btn subtle" onClick={() => setShowCreateTask((value) => !value)}>＋ Add task</button></div>
      <div className="lj-controls">
        <div className="lj-control-group"><label htmlFor="lj-range">View</label><select id="lj-range" value={range} onChange={(event) => setRange(event.target.value)}><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option><option value="all">All activity</option></select></div>
        <div className="lj-range-nav"><button aria-label="Previous date range" onClick={() => setAnchor((value) => changeAnchor(value, range, -1))}>‹</button><b>{headingDate}</b><button aria-label="Next date range" onClick={() => setAnchor((value) => changeAnchor(value, range, 1))}>›</button><button className="lj-today" onClick={() => setAnchor(new Date())}>Today</button></div>
        <div className="lj-control-group"><label htmlFor="lj-topic-filter">Topic</label><select id="lj-topic-filter" value={topicFilter} onChange={(event) => setTopicFilter(event.target.value)}><option value="all">All topics</option>{topicNames.map((topic) => <option key={topic} value={topic}>{topic}</option>)}</select></div>
        <div className="lj-control-group"><label htmlFor="lj-event-filter">Activity</label><select id="lj-event-filter" value={eventFilter} onChange={(event) => setEventFilter(event.target.value)}><option value="all">All activity</option><option value="revision">Planned revisions</option><option value="completed">Completed</option><option value="quizzes">Quizzes</option><option value="notes">Notes</option><option value="weak">Weak topics</option><option value="overdue">Overdue</option></select></div>
        <div className="lj-control-group"><label htmlFor="lj-status-filter">Status</label><select id="lj-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Any status</option><option value="planned">Planned</option><option value="completed">Completed</option><option value="overdue">Overdue</option></select></div>
      </div>

      {showCreateTask && <form className="lj-create-form" onSubmit={addManualTask}>
        <label>Task title<input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="e.g. Review a concept" maxLength={200} required/></label>
        <label>Topic<input value={newTopic} onChange={(event) => setNewTopic(event.target.value)} placeholder="Topic name" maxLength={120} required/></label>
        <label>Duration<select value={newMinutes} onChange={(event) => setNewMinutes(Number(event.target.value))}><option value={15}>15 minutes</option><option value={20}>20 minutes</option><option value={30}>30 minutes</option><option value={45}>45 minutes</option><option value={60}>60 minutes</option></select></label>
        <button className="lj-btn primary" disabled={busy === "create"}>{busy === "create" ? "Saving…" : "Save task"}</button>
      </form>}

      <div className="lj-timeline-layout">
        <div className="lj-timeline-scroll">
          {visibleEvents.length ? <div className="lj-timeline-track">
            {visibleEvents.map((event, index) => {
              const selectedNode = String(selected?.id) === String(event.id);
              const overdue = eventIsOverdue(event, tasks);
              const completed = String(event.status || "").includes("completed");
              const inProgress = event.status === "in_progress";
              return <button key={event.id} className={"lj-timeline-node " + ((event.source === "planner" || event.source === "deadline") ? "planned" : "historical") + (selectedNode ? " active" : "") + (overdue ? " overdue" : "") + (completed ? " completed" : "") + (inProgress ? " in-progress" : "")} onClick={() => { setSelectedId(event.id); setRescheduleAt(""); }} aria-pressed={selectedNode}>
                <span className="lj-node-line" aria-hidden="true"/><span className="lj-node-dot">{completed ? "✓" : event.type === "quiz_completed" ? "Q" : event.type === "note_view" ? "N" : event.source === "planner" ? "↻" : event.source === "deadline" ? "D" : "•"}</span>
                <span className="lj-node-date">{formatDate(event.timestamp, { day: "numeric", month: "short" })}</span><b>{event.title || eventLabel(event)}</b><small>{event.topic || eventLabel(event)}</small><span className={"lj-event-status " + (overdue ? "overdue" : completed ? "completed" : (event.source === "planner" || event.source === "deadline") ? "planned" : inProgress ? "in-progress" : "history")}>{overdue ? "Overdue" : completed ? "Completed" : inProgress ? "In progress" : (event.source === "planner" || event.source === "deadline") ? "Planned" : "Recorded"}</span>
                <span className="lj-timeline-card"><b>{event.title || eventLabel(event)}</b><small>{event.reason || eventLabel(event)}</small><span>{formatDateTime(event.timestamp)}</span></span>
                {index === 0 && <span className="lj-first-marker">EARLIER</span>}
              </button>;
            })}
          </div> : <div className="lj-empty-timeline"><span className="lj-empty-symbol"><Icon name="calendar"/></span><h3>No activity in this view</h3><p>There are no persisted learning events or scheduled tasks matching these filters. Try another date range or complete a learning activity.</p><button className="lj-btn" onClick={() => { setRange("all"); setEventFilter("all"); setStatusFilter("all"); setTopicFilter("all"); }}>Show all activity</button></div>}
        </div>

        <aside className="lj-detail-panel">
          <div className="lj-detail-kicker"><span className={"lj-detail-dot " + (selectedTask && isCompleted(selectedTask) ? "done" : "")}/>{selected ? eventLabel(selected) : "Milestone details"}</div>
          {selected ? <>
            <h3>{selected.title || eventLabel(selected)}</h3>
            <p className="lj-detail-summary">{selected.reason || (selected.source === "planner" ? "A saved revision task from your planner." : "A historical learning event from your activity records.")}</p>
            <div className="lj-detail-facts">
              <div><small>Topic</small><b>{selected.topic || "Not linked"}</b></div>
              <div><small>Date / time</small><b>{formatDateTime(selected.timestamp)}</b></div>
              <div><small>Status</small><b>{selectedTask ? (isCompleted(selectedTask) ? "Completed" : selectedTask.status === "in_progress" ? "In progress" : (eventIsOverdue(selected, tasks) ? "Overdue" : "Planned")) : selected.source === "deadline" ? "Upcoming deadline" : "Recorded activity"}</b></div>
              <div><small>Duration</small><b>{selected.duration_minutes ? selected.duration_minutes + " min estimated" : selectedTask ? (selectedTask.est || "Not specified") + " estimated" : "Not recorded"}</b></div>
              {selectedTask?.priority && <div><small>Priority</small><b className={"lj-priority " + selectedTask.priority}>{selectedTask.priority.toUpperCase()}</b></div>}
              {selectedTask?.original_due_date && <div><small>Original deadline</small><b>{formatDateTime(selectedTask.original_due_date)}</b></div>}
            </div>
            {selectedTask?.evidence && <div className="lj-evidence"><b>Evidence used</b><p>{selectedTask.evidence.mastery == null ? "No measured topic mastery; this task is a diagnostic recommendation." : "Latest weighted mastery: " + Math.round(selectedTask.evidence.mastery * 100) + "%."} {selectedTask.evidence.trend === "declining" ? "Recent performance is declining." : ""}</p><small>Priority factors: {Object.entries(selectedTask.evidence.factors || {}).map(([key, value]) => key + " " + Math.round(Number(value) * 100) + "%").join(" · ")}</small></div>}
            {selectedTask && <div className="lj-detail-actions">
              {!isCompleted(selectedTask) && <button className="lj-btn primary" disabled={busy === "start" || busy === "task-" + selectedTask.id} onClick={() => startRevision(selected)}><Icon name="spark"/> Start revision</button>}
              {!isCompleted(selectedTask) && <button className="lj-btn" disabled={busy === "task-" + selectedTask.id} onClick={() => markComplete(selectedTask)}>{busy === "task-" + selectedTask.id ? "Saving…" : "✓ Mark complete"}</button>}
              {selectedTask.note_id && <button className="lj-btn" onClick={() => onNavigate?.("notes", { noteId: selectedTask.note_id })}><Icon name="notes"/> Open note</button>}
              <button className="lj-btn" onClick={() => { const base = parseDate(selectedTask.scheduled_at || selectedTask.due_date); const date = base || new Date(Date.now() + 86400000); const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); setRescheduleAt(local); }}>Reschedule</button>
              {rescheduleAt && <div className="lj-reschedule"><label htmlFor="lj-reschedule">New date and time</label><input id="lj-reschedule" type="datetime-local" value={rescheduleAt} onChange={(event) => setRescheduleAt(event.target.value)}/><button className="lj-btn primary" disabled={busy === "reschedule"} onClick={saveReschedule}>{busy === "reschedule" ? "Saving…" : "Save time"}</button></div>}
              <button className="lj-btn subtle" onClick={() => { const title = window.prompt("Task title", selectedTask.title); if (title === null || !title.trim()) return; updatePlannerTask(selectedTask.id, { title: title.trim() }).then(() => { toast?.("Task updated.", "teal"); load(); }).catch((err) => toast?.(err.message || "Could not update task.", "coral")); }}>Edit title</button>
            </div>}
            {!selectedTask && <div className="lj-detail-actions"><button className="lj-btn" onClick={() => selected.type === "quiz_completed" ? onNavigate?.("quiz", { quizTopic: selected.topic || "" }) : selected.type === "note_view" ? onNavigate?.("notes") : onNavigate?.("planner")}>{selected.type === "quiz_completed" ? "Practice again" : selected.type === "note_view" ? "Open notes" : "Open planner"} <Icon name="arrow"/></button></div>}
          </> : <div className="lj-empty-detail"><p>Select a timeline node to see its details and actions.</p></div>}
        </aside>
      </div>
    </section>

    <section className="lj-bottom-grid">
      <div className="lj-panel">
        <div className="lj-section-heading"><div><span className="lj-section-icon"><Icon name="calendar"/></span><div><h2>Upcoming revision plan</h2><p>Pending tasks from the same persistent planner used by the dashboard.</p></div></div><button className="lj-btn subtle" onClick={() => onNavigate?.("planner")}>Full planner <Icon name="arrow"/></button></div>
        <div className="lj-upcoming-list">{tasks.filter((task) => !isCompleted(task)).sort((a, b) => (parseDate(a.scheduled_at)?.getTime() ?? Number.MAX_SAFE_INTEGER) - (parseDate(b.scheduled_at)?.getTime() ?? Number.MAX_SAFE_INTEGER)).slice(0, 6).map((task, index) => <button className="lj-upcoming-row" key={task.id} onClick={() => setSelectedId("task-" + task.id)}><span className="lj-upcoming-number">{String(index + 1).padStart(2, "0")}</span><span><b>{task.title}</b><small>{task.topic} · {task.est || "Duration not set"}</small></span><span className={"lj-state " + (task.priority === "high" ? "critical" : task.priority === "med" ? "practice" : "strong")}>{task.priority || "planned"}</span><span className="lj-upcoming-date">{formatDateTime(task.scheduled_at || task.due_date)}</span></button>)}
          {!tasks.some((task) => !isCompleted(task)) && <div className="lj-empty-inline"><span><b>No pending revision tasks</b><p>Generate a schedule after completing topic quizzes, or add a manual revision task.</p></span></div>}
        </div>
      </div>

      <div className="lj-panel lj-preferences-panel">
        <div className="lj-section-heading"><div><span className="lj-section-icon"><Icon name="clock"/></span><div><h2>Schedule preferences</h2><p>Tell StudyAI when revision fits your day.</p></div></div><button className="lj-btn subtle" onClick={() => setShowPreferences((value) => !value)}>{showPreferences ? "Hide" : "Configure"}</button></div>
        {showPreferences && <form className="lj-preferences-form" onSubmit={savePrefs}>
          <label>Daily revision budget (minutes)<input type="number" min="15" max="600" value={preferences.daily_minutes} onChange={(event) => setPreferences((value) => ({ ...value, daily_minutes: Number(event.target.value) }))} required/></label>
          <label>Plan ahead (days)<input type="number" min="1" max="60" value={preferences.planning_days} onChange={(event) => setPreferences((value) => ({ ...value, planning_days: Number(event.target.value) }))} required/></label>
          <label>Start hour (0–23)<input type="number" min="0" max="23" value={preferences.preferred_start_hour} onChange={(event) => setPreferences((value) => ({ ...value, preferred_start_hour: Number(event.target.value) }))} required/></label>
          <label>End hour (1–24)<input type="number" min="1" max="24" value={preferences.preferred_end_hour} onChange={(event) => setPreferences((value) => ({ ...value, preferred_end_hour: Number(event.target.value) }))} required/></label>
          <div className="lj-topic-importance"><b>Topic importance</b><p>Increase a topic's importance when an exam or goal makes it especially relevant.</p>
            {topicNames.length ? topicNames.map((topic) => <label key={topic}><span>{topic}</span><select value={preferences.topic_importance?.[topic] ?? 0.5} onChange={(event) => setPreferences((value) => ({ ...value, topic_importance: { ...(value.topic_importance || {}), [topic]: Number(event.target.value) } }))}><option value={0.25}>Low</option><option value={0.5}>Normal</option><option value={0.75}>High</option><option value={1}>Critical</option></select></label>) : <small>No topics available yet. Complete a quiz to establish tracked topics.</small>}
          </div>
          <button className="lj-btn primary" disabled={busy === "preferences"}>{busy === "preferences" ? "Saving…" : "Save preferences"}</button>
        </form>}
        <form className="lj-deadline-form" onSubmit={addDeadline}>
          <b>{deadlineEditIndex == null ? "Add exam or deadline" : "Edit exam or deadline"}</b>
          <label>Related topic<input value={deadlineTopic} onChange={(event) => setDeadlineTopic(event.target.value)} placeholder="Topic to prioritize" maxLength={120} required/></label>
          <label>Due date<input type="date" value={deadlineDate} onChange={(event) => setDeadlineDate(event.target.value)} required/></label>
          <label>Label (optional)<input value={deadlineText} onChange={(event) => setDeadlineText(event.target.value)} placeholder="Exam / assignment" maxLength={160}/></label>
          <button className="lj-btn" disabled={busy === "deadline"}>{busy === "deadline" ? "Saving…" : deadlineEditIndex == null ? "Save deadline" : "Update deadline"}</button>
          {deadlineEditIndex != null && <button type="button" className="lj-btn subtle" onClick={() => { setDeadlineEditIndex(null); setDeadlineTopic(""); setDeadlineDate(""); setDeadlineText(""); }}>Cancel edit</button>}
        </form>
        {(preferences.deadlines || []).length > 0 && <div className="lj-deadlines">{preferences.deadlines.map((deadline, index) => <div className="lj-deadline-row" key={deadline.topic + deadline.date + index}><span><b>{deadline.text || deadline.topic}</b><small>{deadline.topic} · {formatDate(deadline.date, { day: "numeric", month: "short", year: "numeric" })}</small></span><button className="lj-deadline-edit" type="button" onClick={() => { const parsed = parseDate(deadline.date); const localDay = parsed ? new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000).toISOString().slice(0, 10) : ""; setDeadlineEditIndex(index); setDeadlineTopic(deadline.topic || ""); setDeadlineDate(localDay); setDeadlineText(deadline.text || ""); }}>{ "Edit" }</button><button className="lj-deadline-remove" type="button" aria-label={"Remove " + (deadline.text || deadline.topic)} onClick={() => removeDeadline(index)}>×</button></div>)}</div>}
      </div>
    </section>
    {error && <div className="lj-inline-error" role="alert">{error} <button onClick={load}>Retry</button></div>}
    <footer className="lj-page-footer">STUDYAI · LEARN WITH INTENTION · PRACTICE WITH EVIDENCE</footer>
  </main>;
}
