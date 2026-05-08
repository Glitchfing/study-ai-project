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
import { useToast } from "./hooks/useToast";
import { getDashboard, logActivity } from "./services/api";

const FALLBACK_USER = {
  name: "RUTU",
  initials: "RU",
  role: "Individual Learning",
  streak: 0,
};

export default function App() {
  const [currentView, setCurrentView] = useState("dashboard");
  const [selectedNoteId, setSelectedNoteId] = useState(null);
  const [selectedQuizNoteId, setSelectedQuizNoteId] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);
  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const { toasts, toast } = useToast();

  const refreshDashboard = useCallback(async () => {
    setLoadingDashboard(true);
    try {
      const data = await getDashboard();
      setDashboardData(data);
    } catch {
      setDashboardData(null);
    } finally {
      setLoadingDashboard(false);
    }
  }, []);

  useEffect(() => {
    refreshDashboard();
  }, [refreshDashboard]);

  const trackActivity = useCallback(
    async (event, shouldRefresh = true) => {
      try {
        await logActivity(event);
      } catch {
        // Keep the UI moving even if telemetry fails.
      } finally {
        if (shouldRefresh) {
          refreshDashboard();
        }
      }
    },
    [refreshDashboard]
  );

  function navigate(view, options = {}) {
    if (options.noteId) {
      setSelectedNoteId(options.noteId);
    }
    if (Object.prototype.hasOwnProperty.call(options, "quizNoteId")) {
      setSelectedQuizNoteId(options.quizNoteId);
    } else if (view === "quiz" && !options.noteId) {
      setSelectedQuizNoteId(null);
    }
    setCurrentView(view);
    window.scrollTo(0, 0);
    trackActivity({ kind: "view_opened", view });
  }

  const user = dashboardData?.user || FALLBACK_USER;
  const sharedProps = { onNavigate: navigate, toast, refreshDashboard, trackActivity };

  return (
    <>
      <ToastContainer toasts={toasts} />
      <Sidebar currentView={currentView} onNavigate={navigate} user={user} />
      <div id="main">
        <Topbar user={user} onToast={toast} />
        <div id="view-container">
          {currentView === "dashboard" && (
            <Dashboard
              data={dashboardData}
              loading={loadingDashboard}
              onNavigate={navigate}
              onRefresh={refreshDashboard}
              toast={toast}
            />
          )}
          {currentView === "upload" && <UploadPage {...sharedProps} />}
          {currentView === "notes" && <NotesView {...sharedProps} selectedNoteId={selectedNoteId} />}
          {currentView === "quiz" && <QuizModule {...sharedProps} selectedNoteId={selectedQuizNoteId} />}
          {currentView === "chat" && <ChatInterface {...sharedProps} />}
          {currentView === "planner" && <RevisionPlanner {...sharedProps} />}
        </div>
      </div>
    </>
  );
}
