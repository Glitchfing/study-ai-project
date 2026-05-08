import React from "react";

const NAV = [
  {
    section: "Core",
    items: [
      { view: "dashboard", icon: "⊞", label: "Dashboard" },
      { view: "upload",    icon: "⬆", label: "Upload Content", badge: "NEW", badgeStyle: "teal" },
      { view: "notes",     icon: "◧", label: "Your Notes" },
    ],
  },
  {
    section: "Learning",
    items: [
      { view: "quiz",    icon: "◎", label: "Practice Quiz",   badge: "3" },
      { view: "chat",    icon: "✦", label: "Learn & Ask" },
      { view: "planner", icon: "▦", label: "Revision Planner" },
    ],
  },
];

export default function Sidebar({ currentView, onNavigate, user }) {
  return (
    <aside id="sidebar">
      {/* Logo */}
      <div className="sb-logo">
        <div className="sb-logo-orb">SA</div>
        <div>
          <div className="sb-logo-text">
            Study<em>AI</em>
          </div>
          <div className="sb-logo-version">v2.0 · Phase I</div>
        </div>
      </div>

      {/* User */}
      <div className="sb-user">
        <div className="sb-avatar">{user?.initials || "??"}</div>
        <div className="sb-user-info">
          <p>{user?.name || "Loading…"}</p>
          <small>{user?.role || ""}</small>
        </div>
      </div>

      {/* Navigation */}
      {NAV.map(({ section, items }) => (
        <div className="sb-section" key={section}>
          <div className="sb-section-label">{section}</div>
          {items.map(({ view, icon, label, badge, badgeStyle }) => (
            <div
              key={view}
              className={`sb-item${currentView === view ? " active" : ""}`}
              onClick={() => onNavigate(view)}
            >
              <span className="sb-icon">{icon}</span>
              {label}
              {badge && (
                <span className={`sb-badge${badgeStyle === "teal" ? " teal" : ""}`}>
                  {badge}
                </span>
              )}
            </div>
          ))}
        </div>
      ))}

      {/* Mode select */}
      <div className="sb-bottom">
        <div className="sb-mode-label">View Mode</div>
        <select className="sb-mode-select">
          <option>👤 Student</option>
          <option>👩‍🏫 Teacher</option>
          <option>📊 Analytics</option>
        </select>
      </div>
    </aside>
  );
}