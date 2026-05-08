import React, { useState, useRef, useEffect } from "react";
import { sendChatMessage } from "../services/api";

const QUICK_BTNS = [
  "Explain tokenization",
  "What is BERT?",
  "Summarize my notes",
  "Show weak areas",
  "Quick quiz",
];

let msgId = 0;

function formatMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

export default function ChatInterface({ toast, refreshDashboard }) {
  const [messages, setMessages] = useState([
    {
      id: ++msgId,
      role: "ai",
      text:
        "Hi! I'm your **StudyAI** assistant. Ask me anything about your study materials, request a quiz, or get topic explanations!\n\nTry the quick buttons below 👇",
    },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const winRef = useRef();
  const inputRef = useRef();

  useEffect(() => {
    if (winRef.current) winRef.current.scrollTop = winRef.current.scrollHeight;
  }, [messages, typing]);

  async function send(text) {
    const msg = (text || input).trim();
    if (!msg) return;
    setInput("");
    setMessages((prev) => [...prev, { id: ++msgId, role: "user", text: msg }]);
    setTyping(true);
    try {
      const data = await sendChatMessage(msg, null, []);
      setMessages((prev) => [...prev, { id: ++msgId, role: "ai", text: data.response }]);
      if (typeof refreshDashboard === "function") {
        refreshDashboard();
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: ++msgId, role: "ai", text: "⚠️ Sorry, I couldn't connect to the server. Please try again." },
      ]);
    } finally {
      setTyping(false);
    }
  }

  return (
    <div className="view active" id="view-chat">
      <div className="section-label">Learn & Ask</div>

      <div className="chat-container card">
        {/* Header */}
        <div className="chat-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div className="chat-msg-avatar ai" style={{ width: 34, height: 34 }}>AI</div>
            <div>
              <div style={{ fontFamily: "'Syne',sans-serif", fontWeight: 700, fontSize: 13 }}>
                StudyAI Assistant
              </div>
              <div style={{ fontSize: 10, color: "var(--c-aqua)" }}>● Online</div>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="chat-window" ref={winRef}>
          {messages.map((m) => (
            <div key={m.id} className={`chat-msg ${m.role}`}>
              <div className={`chat-msg-avatar ${m.role}`}>
                {m.role === "ai" ? "AI" : "AC"}
              </div>
              <div
                className="chat-bubble"
                dangerouslySetInnerHTML={{ __html: formatMarkdown(m.text) }}
              />
            </div>
          ))}
          {typing && (
            <div className="chat-msg ai">
              <div className="chat-msg-avatar ai">AI</div>
              <div className="chat-bubble">
                <div className="chat-typing">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="chat-footer">
          <div className="chat-quick-btns">
            {QUICK_BTNS.map((q) => (
              <button key={q} className="chat-quick-btn" onClick={() => send(q)}>
                {q}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
            <div className="chat-input-wrap">
              <textarea
                ref={inputRef}
                className="chat-input"
                placeholder="Ask about any topic, request explanations, or get a quiz…"
                value={input}
                rows={1}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
              />
            </div>
            <button
              className="btn btn-primary"
              style={{ height: 44, padding: "0 16px" }}
              onClick={() => send()}
              disabled={typing || !input.trim()}
            >
              ➤
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
