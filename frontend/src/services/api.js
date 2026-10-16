/**
 * services/api.js
 * Centralised API client for StudyAI Platform.
 * All fetch calls go through here — swap BASE_URL for production.
 */

const BASE_URL =
  window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : import.meta.env.VITE_API_URL;

export const getAssetUrl = (path) => {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
};

async function request(method, path, body = null, isFormData = false) {
  const opts = { method };
  if (body !== null && body !== undefined) {
    if (isFormData) opts.body = body;
    else {
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

// Dashboard
export const getDashboard = () => request("GET", "/dashboard");

// Personalized recommendations
export const getRecommendations = (limit = 3, includeHistory = false) => {
  const params = new URLSearchParams({ limit: String(limit), include_history: String(includeHistory) });
  return request("GET", `/recommendations?${params.toString()}`);
};
export const refreshRecommendations = (limit = 3) =>
  request("POST", `/recommendations/refresh?limit=${encodeURIComponent(limit)}`);
export const startRecommendation = (id, note = null) =>
  request("POST", `/recommendations/${encodeURIComponent(id)}/start`, note ? { note } : {});
export const completeRecommendation = (id, note = null) =>
  request("POST", `/recommendations/${encodeURIComponent(id)}/complete`, note ? { note } : {});
export const dismissRecommendation = (id, note = null) =>
  request("POST", `/recommendations/${encodeURIComponent(id)}/dismiss`, note ? { note } : {});

// Upload
export const uploadFile = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return request("POST", "/upload", fd, true);
};
export const uploadFiles = (files) => {
  const fd = new FormData();
  files.forEach((file) => fd.append("files", file));
  return request("POST", "/upload", fd, true);
};

// Notes
export const getNotesList = () => request("GET", "/notes");
export const getNote = (id, format = "cornell") =>
  request("GET", `/notes/${id}?format=${format}`);
export const deleteNote = (id) => request("DELETE", `/notes/${encodeURIComponent(id)}`);

// Quiz
export const getQuiz = (topic = "all", limit = 5, noteId = null, quizTopic = null) => {
  const params = new URLSearchParams({ topic, limit: String(limit) });
  if (noteId) params.set("note_id", noteId);
  if (quizTopic) params.set("quiz_topic", quizTopic);
  return request("GET", `/quiz?${params.toString()}`);
};
export const saveQuizAttempt = (attempt) => request("POST", "/quiz/attempts", attempt);
export const getQuizAttempts = (noteId = null, limit = 20) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (noteId) params.set("note_id", noteId);
  return request("GET", `/quiz/attempts?${params.toString()}`);
};

// Chat
export const sendChatMessage = (message, context = null, history = []) =>
  request("POST", "/chat", { message, context, history });

// Planner and Learning Journey
export const getPlanner = (start = null, end = null) => {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const query = params.toString();
  return request("GET", "/planner" + (query ? "?" + query : ""));
};
export const toggleTask = (task_id, done) =>
  request("POST", "/planner/toggle", { task_id, done });
export const updatePlannerTask = (task_id, changes) =>
  request("PATCH", `/planner/tasks/${encodeURIComponent(task_id)}`, changes);
export const createPlannerTask = (task) => request("POST", "/planner/tasks", task);
export const autoSchedule = () => request("POST", "/planner/auto-schedule");
export const getPlannerPreferences = () => request("GET", "/planner/preferences");
export const savePlannerPreferences = (preferences) => request("PUT", "/planner/preferences", preferences);

// Measured study-session timer. The server owns timestamps and persistence.
export const getActiveStudySession = () => request("GET", "/activity/study-sessions/active");
export const startStudySession = (topic = null) =>
  request("POST", "/activity/study-sessions/start", { topic });
export const completeStudySession = (session_id) =>
  request("POST", "/activity/study-sessions/complete", { session_id });
export const pauseStudySession = (session_id) =>
  request("POST", "/activity/study-sessions/pause", { session_id });
export const resumeStudySession = (session_id) =>
  request("POST", "/activity/study-sessions/resume", { session_id });
export const heartbeatStudySession = (session_id) =>
  request("POST", "/activity/study-sessions/heartbeat", { session_id });
export const getStudySessionHistory = (start, end) => {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return request("GET", "/activity/study-sessions/history" + (params.size ? "?" + params.toString() : ""));
};

// Activity
export const logActivity = (event) => request("POST", "/activity", event);

// Targeted Topic Study
export const uploadAndTargetStudy = (files, query, topK = 12, maxChunks = 18) => {
  const fd = new FormData();
  files.forEach((file) => fd.append("files", file));
  fd.append("query", query);
  fd.append("top_k", String(topK));
  fd.append("max_chunks", String(maxChunks));
  return request("POST", "/study/upload-and-target", fd, true);
};
export const generateTargetedStudy = (documentId, query, options = {}) => request("POST", "/study/targeted", {
  document_id: documentId, query, top_k: options.topK || 12, max_chunks: options.maxChunks || 18,
  note_depth: options.noteDepth || "deep", include_examples: options.includeExamples !== false,
  include_diagrams: options.includeDiagrams !== false,
});
export const retrieveTargetedChunks = (documentId, query, topK = 12, maxChunks = 18) =>
  request("POST", "/study/targeted-retrieval", { document_id: documentId, query, top_k: topK, max_chunks: maxChunks });
export const getIndexedDocuments = () => request("GET", "/study/documents");
