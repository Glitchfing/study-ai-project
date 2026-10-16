import React from "react";

const NAV = [
  { view: "dashboard", icon: "home", label: "Dashboard" },
  { view: "upload", icon: "upload", label: "Upload Content" },
  { view: "notes", icon: "notes", label: "My Notes" },
  { view: "quiz", icon: "quiz", label: "Quizzes" },
  { view: "chat", icon: "chat", label: "Learn & Ask" },
  { view: "journey", icon: "chart", label: "Learning Journey" },
  { view: "planner", icon: "calendar", label: "Revision Planner" },
];

const icons = {
  home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z" /></>,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5" /></>,
  notes: <><path d="M6 3h9l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM14 3v5h5M8 12h8M8 16h6" /></>,
  quiz: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M8 9h.01M12 9h.01M16 9h.01M8 14l2 2 5-5" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 14h3M8 17h6" /></>,
  chart: <><path d="M4 20V12h4v8M10 20V5h4v15M16 20V9h4v11" /></>,
  chat: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H6l-3 2v-6.5A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8 11h8M8 14h5" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="m19 13 2 1-2 3-2-1a7 7 0 0 1-2 1l-.5 2h-4L10 17a7 7 0 0 1-2-1l-2 1-2-3 2-1a7 7 0 0 1 0-2L4 10l2-3 2 1a7 7 0 0 1 2-1l.5-2h4l.5 2a7 7 0 0 1 2 1l2-1 2 3-2 1a7 7 0 0 1 0 2Z" /></>,
};

function SidebarIcon({ name }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icons[name] || icons.home}</svg>;
}

export default function Sidebar({ currentView, onNavigate, user, isOpen = false, onClose, toast }) {
  return <>
    <button className={`rf-sidebar-scrim${isOpen ? " visible" : ""}`} onClick={onClose} aria-label="Close navigation" tabIndex={isOpen ? 0 : -1} />
    <aside className={`rf-app-sidebar${isOpen ? " rf-app-sidebar-open" : ""}`} aria-label="Main navigation">
      <div className="rf-brand">
        <span className="rf-logo">SA</span>
        <span><b>StudyAI</b><small>AI-powered learning</small></span>
      </div>
      <nav className="rf-nav">
        {NAV.map(({ view, icon, label }) => (
          <button key={view} type="button" className={`rf-nav-item${currentView === view ? " active" : ""}`} aria-current={currentView === view ? "page" : undefined} onClick={() => onNavigate(view)}>
            <SidebarIcon name={icon} />{label}
          </button>
        ))}
        <div className="rf-nav-rule" />
        <button type="button" className="rf-nav-item" onClick={() => toast?.("Settings page is planned for a later release.", "teal")}>
          <SidebarIcon name="settings" />Settings
        </button>
      </nav>
      <div className="rf-app-sidebar-foot">LEARN · PRACTICE · GROW</div>
    </aside>
  </>;
}
