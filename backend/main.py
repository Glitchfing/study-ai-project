"""
StudyAI Platform — FastAPI Backend
Run: uvicorn main:app --reload --port 8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routes import activity, dashboard, upload, notes, quiz, chat, planner

Path("static/diagrams").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="StudyAI API", version="2.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(activity.router,  prefix="/activity",  tags=["Activity"])
app.include_router(upload.router,    prefix="/upload",    tags=["Upload"])
app.include_router(notes.router,     prefix="/notes",     tags=["Notes"])
app.include_router(quiz.router,      prefix="/quiz",      tags=["Quiz"])
app.include_router(chat.router,      prefix="/chat",      tags=["Chat"])
app.include_router(planner.router,   prefix="/planner",   tags=["Planner"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}
