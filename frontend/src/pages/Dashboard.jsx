import React from "react";

function KpiCard({ kpi, onNavigate }) {
  return (
    <div
      className="card kpi-card"
      onClick={() => kpi.link && onNavigate(kpi.link)}
      style={{ cursor: kpi.link ? "pointer" : "default" }}
    >
      <div className="kpi-icon">{kpi.icon}</div>
      <div className="kpi-label">{kpi.label}</div>
      <div className="kpi-value">
        {kpi.value}
        {kpi.suffix && <sup>{kpi.suffix}</sup>}
      </div>
      <div className={`kpi-delta${kpi.positive ? "" : " neg"}`}>{kpi.delta}</div>
    </div>
  );
}

function TopicCard({ topic, onNavigate }) {
  const colorMap = {
    teal: "var(--c-bright)",
    coral: "var(--c-coral)",
    aqua: "var(--c-aqua)",
  };
  const color = colorMap[topic.color] || "var(--c-bright)";
  const gradMap = {
    teal: "linear-gradient(90deg,var(--c-bright),var(--c-mint))",
    coral: "linear-gradient(90deg,var(--c-coral),#c1694f)",
    aqua: "linear-gradient(90deg,var(--c-aqua),var(--c-sky))",
  };

  return (
    <div className="card orb-card" onClick={() => onNavigate("notes")} style={{ cursor: "pointer" }}>
      <div className="orb-canvas-wrap">
        <div
          style={{
            width: 50,
            height: 50,
            borderRadius: 12,
            background: `radial-gradient(circle at 35% 35%, ${color}33, ${color}11)`,
            border: `1px solid ${color}44`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 18,
          }}
        >
          {topic.color === "teal" ? "🔤" : topic.color === "coral" ? "🤖" : "🌳"}
        </div>
      </div>
      <div className="orb-meta">
        <div className="orb-name">{topic.name}</div>
        <div className="orb-sub">{topic.sub}</div>
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${topic.pct}%`, background: gradMap[topic.color] }}
          />
        </div>
      </div>
      <span style={{ fontFamily: "'Syne',sans-serif", fontWeight: 800, fontSize: 17, color }}>
        {topic.pct}%
      </span>
    </div>
  );
}

function BarChart({ data }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="bar-chart-wrap">
      {data.map((d) => (
        <div className="bc-col" key={d.month}>
          <div
            className="bc-bar"
            style={{
              height: `${(d.value / max) * 80}px`,
              background: "linear-gradient(180deg, var(--c-bright), var(--c-ocean))",
            }}
            title={`${d.month}: ${d.value}`}
          />
          <div className="bc-lbl">{d.month.slice(0, 3)}</div>
        </div>
      ))}
    </div>
  );
}

function Heatmap({ cells = [] }) {
  if (!cells.length) {
    return <div style={{ color: "var(--muted)", fontSize: 12 }}>No activity yet.</div>;
  }

  return (
    <div className="heatmap-wrap">
      {cells.map((col, w) => (
        <div className="hm-col" key={w}>
          {col.map((cell, d) => (
            <div key={d} className={`hm-cell ${cell.lvl}`} title={cell.tip} />
          ))}
        </div>
      ))}
    </div>
  );
}

function activityLabel(entry) {
  switch (entry.kind) {
    case "upload_processed":
      return `Uploaded ${entry.filename || "a file"}`;
    case "quiz_completed":
      return `Finished quiz with ${entry.score ?? 0}%`;
    case "note_view":
      return `Opened ${entry.title || "a note"} (${entry.format || "cornell"})`;
    case "planner_task_done":
      return `${entry.done ? "Completed" : "Reopened"} task ${entry.task_id}`;
    case "chat_message":
      return "Asked the assistant a question";
    case "view_opened":
      return `Opened ${entry.view}`;
    default:
      return entry.kind.replaceAll("_", " ");
  }
}

export default function Dashboard({ data, loading, onNavigate, onRefresh, toast }) {
  if (loading) {
    return (
      <div style={{ padding: 40, color: "var(--muted)", textAlign: "center" }}>
        Loading dashboard...
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: 40, color: "var(--muted)", textAlign: "center" }}>
        Dashboard data is unavailable.
      </div>
    );
  }

  return (
    <div className="view active" id="view-dashboard">
      <div className="section-label">Performance Overview</div>
      <div className="kpi-grid">
        {data.kpis.map((k) => (
          <KpiCard key={k.id} kpi={k} onNavigate={onNavigate} />
        ))}
      </div>

      <div className="section-label">Topic Mastery</div>
      <div className="orb-row">
        {data.topics.map((t) => (
          <TopicCard key={t.id} topic={t} onNavigate={onNavigate} />
        ))}
      </div>

      <div className="dash-grid">
        <div className="card" style={{ padding: "18px 20px" }}>
          <div className="card-header">
            <div className="card-title">📅 Activity Heatmap</div>
            <span
              className="card-action"
              onClick={() => toast("📅 Heatmap now reflects your real sessions", "teal")}
            >
              {data.heatmap_weeks} weeks
            </span>
          </div>
          <Heatmap cells={data.activity_heatmap} />
          <div className="hm-legend">
            <span>Less</span>
            <div style={{ display: "flex", gap: 3 }}>
              {["", "l1", "l2", "l3", "l4"].map((c, i) => (
                <div key={i} className={`hm-cell ${c}`} style={{ cursor: "default" }} />
              ))}
            </div>
            <span>More</span>
          </div>
        </div>

        <div className="card stats-stack">
          <div className="card-title" style={{ marginBottom: 2 }}>
            📊 Long-term Stats
          </div>
          {[
            { label: "⚡ Total Activities", val: data.long_term_stats.total_activities, cls: "accent" },
            { label: "🔥 Longest Streak", val: data.long_term_stats.longest_streak, cls: "" },
            { label: "📅 Active Days", val: data.long_term_stats.active_days, cls: "warm" },
          ].map(({ label, val, cls }) => (
            <div className="stat-pill" key={label}>
              <div className="stat-pill-label">{label}</div>
              <div className={`stat-pill-val ${cls}`}>{val}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="section-label">Analytics & Insights</div>
      <div className="bottom-grid">
        <div className="card" style={{ padding: "18px 20px" }}>
          <div className="card-header">
            <div className="card-title">📈 Learning Progress</div>
            <span className="card-action">12 months</span>
          </div>
          <BarChart data={data.bar_chart} />
        </div>

        <div className="card" style={{ padding: "18px 20px" }}>
          <div className="card-header">
            <div className="card-title">📝 Recent Quizzes</div>
            <span className="card-action" onClick={() => onNavigate("quiz")}>
              All Quizzes →
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
            {data.recent_quizzes.length ? (
              data.recent_quizzes.map((q) => (
                <div
                  key={`${q.title}-${q.score}`}
                  className="tip-row"
                  onClick={() => onNavigate("quiz")}
                  style={{ cursor: "pointer" }}
                >
                  <div
                    className="tip-ico"
                    style={{
                      background: `rgba(${
                        q.variant === "green" ? "100,182,172" : q.variant === "coral" ? "226,149,120" : "17,157,164"
                      },0.15)`,
                    }}
                  >
                    {q.icon}
                  </div>
                  <div className="tip-body">
                    <strong>{q.title}</strong>
                    <br />
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                      {q.score}% · {q.difficulty}
                    </span>
                  </div>
                  <span className={`tag tag-${q.variant}`}>{q.score}%</span>
                </div>
              ))
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 12 }}>No quiz activity yet.</div>
            )}
          </div>
        </div>

        <div className="card" style={{ padding: "18px 20px" }}>
          <div className="card-header">
            <div className="card-title">💡 Live Activity</div>
            <span className="card-action" onClick={onRefresh}>
              Refresh ↻
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
            {(data.recent_activity || []).slice(0, 4).map((entry) => (
              <div key={`${entry.timestamp}-${entry.kind}`} className="tip-row">
                <div className="tip-ico">•</div>
                <div className="tip-body">
                  <strong>{activityLabel(entry)}</strong>
                  <br />
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>{entry.timestamp}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="card-title" style={{ marginBottom: 8 }}>
            💡 AI Tips
          </div>
          <div className="tips-list">
            {data.tips.length ? (
              data.tips.map((tip) => (
                <div className="tip-row" key={tip.title}>
                  <div className="tip-ico">{tip.icon}</div>
                  <div className="tip-body">
                    <strong>{tip.title}:</strong> {tip.body}
                  </div>
                </div>
              ))
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 12 }}>Tips will appear after you start learning.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
