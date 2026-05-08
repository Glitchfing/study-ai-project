import React, { useMemo } from "react";

export default function Topbar({ user, onToast }) {
  const dateStr = useMemo(
    () =>
      new Date().toLocaleDateString("en-US", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      }),
    []
  );

  return (
    <div id="topbar">
      <div className="tb-greeting">
        <h2>Welcome back, {user?.name?.split(" ")[0] || "there"}! 👋</h2>
        <p>{dateStr}</p>
      </div>

      <div className="tb-streak" title="Your current study streak">
        🔥 <span>{user?.streak ?? "—"}</span> Day Streak
      </div>

      <div
        className="tb-btn"
        onClick={() => onToast("🔔 No new notifications", "teal")}
        title="Notifications"
      >
        🔔<span className="tb-dot" />
      </div>

      <div
        className="tb-btn"
        onClick={() => onToast("⚙️ Settings coming in Phase II", "teal")}
        title="Settings"
      >
        ⚙️
      </div>
    </div>
  );
}
