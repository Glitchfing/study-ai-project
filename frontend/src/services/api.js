/**
 * services/api.js
 * Centralised API client for StudyAI Platform.
 * All fetch calls go through here — swap BASE_URL for production.
 */

const BASE_URL =
  window.location.hostname === "localhost" ? "http://localhost:8000" : "/api";

export const getAssetUrl = (path) => {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
};

async function request(method, path, body = null, isFormData = false) {
  const opts = { method };

  if (body) {
    if (isFormData) {
      opts.body = body; // FormData — let browser set Content-Type
    } else {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
  }

  const res = await fetch(`${BASE_URL}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "API error");
  }
  return res.json();
}

// ── Dashboard ────────────────────────────────────────────────────────────────
export const getDashboard = () => request("GET", "/dashboard");

// ── Upload ───────────────────────────────────────────────────────────────────
export const uploadFile = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return request("POST", "/upload", fd, true);
};

// ── Notes ────────────────────────────────────────────────────────────────────
export const getNotesList = () => request("GET", "/notes");
export const getNote = (id, format = "cornell") =>
  request("GET", `/notes/${id}?format=${format}`);

// ── Quiz ─────────────────────────────────────────────────────────────────────
export const getQuiz = (topic = "all", limit = 5, noteId = null) => {
  const params = new URLSearchParams({ topic, limit: String(limit) });
  if (noteId) params.set("note_id", noteId);
  return request("GET", `/quiz?${params.toString()}`);
};
export const saveQuizAttempt = (attempt) =>
  request("POST", "/quiz/attempts", attempt);
export const getQuizAttempts = (noteId = null, limit = 20) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (noteId) params.set("note_id", noteId);
  return request("GET", `/quiz/attempts?${params.toString()}`);
};

// ── Chat ─────────────────────────────────────────────────────────────────────
export const sendChatMessage = (message, context = null, history = []) =>
  request("POST", "/chat", { message, context, history });

// ── Planner ──────────────────────────────────────────────────────────────────
export const getPlanner = () => request("GET", "/planner");
export const toggleTask = (task_id, done) =>
  request("POST", "/planner/toggle", { task_id, done });
export const autoSchedule = () => request("POST", "/planner/auto-schedule");

// Activity
export const logActivity = (event) => request("POST", "/activity", event);
