import React from "react";

export default function ToastContainer({ toasts }) {
  return (
    <div className="toast-container">
      {toasts.map(({ id, message, type }) => (
        <div
          key={id}
          className="toast"
          style={{
            borderColor:
              type === "coral"
                ? "rgba(226,149,120,0.35)"
                : "var(--border2)",
          }}
        >
          {message}
        </div>
      ))}
    </div>
  );
}