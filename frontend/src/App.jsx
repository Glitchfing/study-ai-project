import React, { useCallback, useEffect, useState } from "react";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import ToastContainer from "./components/ToastContainer";
import Dashboard from "./pages/Dashboard";
import UploadPage from "./pages/UploadPage";
import NotesView from "./pages/NotesView";
import QuizModule from "./pages/QuizModule";
import ChatInterface from "./pages/ChatInterface";
import RevisionPlanner from "./pages/RevisionPlanner";
import LearningJourney from "./pages/LearningJourney";
import { useToast } from "./hooks/useToast";
import { getActiveStudySession, getDashboard, heartbeatStudySession, logActivity } from "./services/api";

const FALLBACK_USER = { name: "RUTU", initials: "RU", role: "Individual Learning", streak: 0 };
const initialView = () => window.location.pathname === "/learning-journey" ? "journey" : "dashboard";

export default function App() {
  const [currentView, setCurrentView] = useState(initialView);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selectedNoteId, setSelectedNoteId] = useState(null);
  const [selectedQuizNoteId, setSelectedQuizNoteId] = useState(null);
  const [selectedQuizTopic, setSelectedQuizTopic] = useState("");
  const [selectedRecommendationId, setSelectedRecommendationId] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);
  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const { toasts, toast } = useToast();

  const refreshDashboard = useCallback(async () => {
    setLoadingDashboard(true);
    try { setDashboardData(await getDashboard()); }
    catch { setDashboardData(null); }
    finally { setLoadingDashboard(false); }
  }, []);

  useEffect(() => { refreshDashboard(); }, [refreshDashboard]);

  // Keep the server-owned study session alive while the learner navigates between
  // planner, notes, quiz, chat, and dashboard views. Missing heartbeats auto-pause
  // the session on the backend rather than counting unobserved time.
  useEffect(() => {
    let sessionId = null;
    let inFlight = false;
    let mounted = true;

    async function heartbeat() {
      if (inFlight || !mounted) return;
      inFlight = true;
      try {
        if (sessionId) {
          try {
            await heartbeatStudySession(sessionId);
            return;
          } catch {
            sessionId = null;
          }
        }
        const result = await getActiveStudySession();
        sessionId = result?.active?.status === "active" ? result.active.session_id : null;
      } catch {
        // Timer recovery is best effort; the backend's stale-session guard
        // remains authoritative if the client is offline.
        sessionId = null;
      } finally {
        inFlight = false;
      }
    }

    heartbeat();
    const timer = window.setInterval(heartbeat, 45_000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const onPopState = (event) => {
      const view = event.state?.view;
      setCurrentView(view || (window.location.pathname === "/learning-journey" ? "journey" : "dashboard"));
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const trackActivity = useCallback(async (event, shouldRefresh = true) => {
    try { await logActivity(event); }
    catch { /* Keep the UI responsive if activity telemetry is unavailable. */ }
    finally { if (shouldRefresh) refreshDashboard(); }
  }, [refreshDashboard]);

  function navigate(view, options = {}) {
    if (options.noteId) setSelectedNoteId(options.noteId);
    if (Object.prototype.hasOwnProperty.call(options, "quizNoteId")) setSelectedQuizNoteId(options.quizNoteId);
    else if (view === "quiz" && !options.noteId) setSelectedQuizNoteId(null);
    if (Object.prototype.hasOwnProperty.call(options, "quizTopic")) setSelectedQuizTopic(options.quizTopic || "");
    else if (view === "quiz") setSelectedQuizTopic("");
    if (Object.prototype.hasOwnProperty.call(options, "recommendationId")) setSelectedRecommendationId(options.recommendationId || null);
    else if (view === "quiz") setSelectedRecommendationId(null);
    const targetPath = view === "journey" ? "/learning-journey" : "/";
    if (window.location.pathname !== targetPath || window.history.state?.view !== view) {
      window.history.pushState({ view }, "", targetPath);
    }
    setCurrentView(view);
    setSidebarOpen(false);
    window.scrollTo(0, 0);
    trackActivity({ kind: "view_opened", view });
  }

  const user = dashboardData?.user || FALLBACK_USER;
  const sharedProps = { onNavigate: navigate, toast, refreshDashboard, trackActivity };

  return <>
    <ToastContainer toasts={toasts} />
    <Sidebar currentView={currentView} onNavigate={navigate} user={user} isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} toast={toast} />
    <div id="main">
      {currentView !== "dashboard" && <Topbar user={user} onToast={toast} onToggleSidebar={() => setSidebarOpen((open) => !open)} />}
      <div id="view-container" className={currentView === "dashboard" ? "dashboard-host" : ""}>
        {currentView === "dashboard" && <Dashboard data={dashboardData} loading={loadingDashboard} onNavigate={navigate} onRefresh={refreshDashboard} toast={toast} onToggleSidebar={() => setSidebarOpen((open) => !open)} />}
        {currentView === "upload" && <UploadPage {...sharedProps} />}
        {currentView === "notes" && <NotesView {...sharedProps} selectedNoteId={selectedNoteId} />}
        {currentView === "quiz" && <QuizModule {...sharedProps} selectedNoteId={selectedQuizNoteId} selectedQuizTopic={selectedQuizTopic} selectedRecommendationId={selectedRecommendationId} />}
        {currentView === "chat" && <ChatInterface {...sharedProps} />}
        {currentView === "planner" && <RevisionPlanner {...sharedProps} />}
        {currentView === "journey" && <LearningJourney {...sharedProps} />}
      </div>
    </div>
  </>;
}
