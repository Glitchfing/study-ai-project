import React, { useEffect, useState } from "react";
import { getPlanner, toggleTask, autoSchedule } from "../services/api";

const WEEK_DAYS = ["M", "T", "W", "T", "F", "S", "S"];

export default function RevisionPlanner({ toast, refreshDashboard }) {
  const [tasks, setTasks] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [streak] = useState(7);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPlanner()
      .then((data) => {
        setTasks(data.tasks);
        setDeadlines(data.deadlines);
      })
      .catch(() => toast("⚠️ Could not load planner", "coral"))
      .finally(() => setLoading(false));
  }, []);

  async function handleToggle(id, currentDone) {
    const newDone = !currentDone;
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: newDone } : t)));
    try {
      await toggleTask(id, newDone);
      if (newDone) toast("✅ Task completed! Keep going!", "teal");
      if (typeof refreshDashboard === "function") {
        refreshDashboard();
      }
    } catch {
      // revert
      setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: currentDone } : t)));
      toast("⚠️ Could not update task", "coral");
    }
  }

  async function handleAutoSchedule() {
    toast("✨ AI generating optimal schedule…", "teal");
    try {
      const res = await autoSchedule();
      toast(`📅 ${res.message}`, "teal");
    } catch {
      toast("⚠️ Auto-schedule failed", "coral");
    }
  }

  const todayTasks = tasks.filter((t) => t.day === "today");
  const upcomingTasks = tasks.filter((t) => t.day === "upcoming");
  const doneTodayCount = todayTasks.filter((t) => t.done).length;
  const progressPct = todayTasks.length ? (doneTodayCount / todayTasks.length) * 100 : 0;

  return (
    <div className="view active" id="view-planner">
      <div className="section-label">Revision Planner</div>

      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <button className="btn btn-primary btn-sm" onClick={handleAutoSchedule}>
          ✨ AI Auto-Schedule
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => toast("📥 Export coming soon", "teal")}>
          📥 Export
        </button>
      </div>

      <div className="planner-layout">
        {/* Main tasks */}
        <div className="planner-main">
          {loading ? (
            <div style={{ color: "var(--muted)", padding: 16 }}>Loading tasks…</div>
          ) : (
            <>
              {/* Today */}
              <div className="card" style={{ padding: "16px 18px" }}>
                <div className="card-header">
                  <div className="card-title">📅 Today's Tasks</div>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>
                    {doneTodayCount}/{todayTasks.length} done
                  </span>
                </div>
                <div className="progress-bar" style={{ marginBottom: 14 }}>
                  <div
                    className="progress-fill"
                    style={{
                      width: `${progressPct}%`,
                      background: "linear-gradient(90deg,var(--c-bright),var(--c-aqua))",
                    }}
                  />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {todayTasks.map((t) => (
                    <TaskRow key={t.id} task={t} onToggle={handleToggle} />
                  ))}
                </div>
              </div>

              {/* Upcoming */}
              <div className="card" style={{ padding: "16px 18px" }}>
                <div className="card-title" style={{ marginBottom: 12 }}>📆 Upcoming</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {upcomingTasks.map((t) => (
                    <div key={t.id} className="planner-task" style={{ opacity: 0.75 }}>
                      <div className="task-checkbox" />
                      <div className="task-info">
                        <div className="task-title">{t.title}</div>
                        <div className="task-meta">
                          <span>{t.topic}</span>
                          <span>⏱ {t.est}</span>
                        </div>
                      </div>
                      <span className="task-time">{t.date || ""}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Sidebar */}
        <div className="planner-sidebar">
          {/* Streak card */}
          <div className="streak-card">
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>Current Streak</div>
            <div className="streak-big">🔥 {streak}</div>
            <div className="streak-sub">days in a row</div>
            <div className="streak-mini-grid">
              {WEEK_DAYS.map((day, i) => (
                <div
                  key={i}
                  className={`streak-day ${i < streak % 7 ? "done" : i === streak % 7 ? "today" : "future"}`}
                >
                  {day}
                </div>
              ))}
            </div>
          </div>

          {/* Deadlines */}
          <div className="card" style={{ padding: "16px 18px" }}>
            <div className="card-title" style={{ marginBottom: 12 }}>📅 Upcoming Deadlines</div>
            <div className="upcoming-list">
              {deadlines.map((d, i) => (
                <div key={i} className="upcoming-item">
                  <div className="upcoming-dot" style={{ background: d.color }} />
                  <div className="upcoming-text">{d.text}</div>
                  <div className="upcoming-date">{d.date}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Progress card */}
          <div className="card" style={{ padding: "16px 18px" }}>
            <div className="card-title" style={{ marginBottom: 10 }}>📊 Today's Progress</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                  <span>Tasks Done</span>
                  <span>{doneTodayCount}/{todayTasks.length}</span>
                </div>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${progressPct}%`,
                      background: "linear-gradient(90deg,var(--c-bright),var(--c-aqua))",
                    }}
                  />
                </div>
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                  <span>Study Time Today</span>
                  <span>1h 20m</span>
                </div>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: "55%", background: "linear-gradient(90deg,var(--c-coral),#c1694f)" }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TaskRow({ task, onToggle }) {
  const prioMap = { high: "coral", med: "teal", low: "green" };
  return (
    <div className={`planner-task${task.done ? " done" : ""}`} onClick={() => onToggle(task.id, task.done)}>
      <div className={`task-checkbox${task.done ? " checked" : ""}`}>
        {task.done && "✓"}
      </div>
      <div className="task-info">
        <div className="task-title">{task.title}</div>
        <div className="task-meta">
          <span>{task.topic}</span>
          <span>⏱ {task.est}</span>
        </div>
      </div>
      <span className={`task-prio ${task.priority}`}>{task.priority?.toUpperCase()}</span>
    </div>
  );
}
