"""
StudyAI Platform — FastAPI Backend
Run locally:
python -m uvicorn main:app --reload

Production:
uvicorn main:app --host 0.0.0.0 --port 10000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routes import (
    activity,
    dashboard,
    upload,
    notes,
    quiz,
    chat,
    planner,
)

# =====================================================
# CREATE STATIC DIRECTORIES
# =====================================================

Path("static/diagrams").mkdir(
    parents=True,
    exist_ok=True,
)

# =====================================================
# FASTAPI APP
# =====================================================

app = FastAPI(
    title="StudyAI API",
    version="2.0.0",
)

# =====================================================
# STATIC FILES
# =====================================================

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)

# =====================================================
# CORS
# =====================================================
# Localhost for development
# Vercel domains for production

origins = [
    "http://localhost:5173",
    "http://localhost:3000",

    "https://study-ai-project.vercel.app",

    # Allow all Vercel preview deployments
    "https://*.vercel.app",
]

app.add_middleware(
    CORSMiddleware,

    allow_origins=origins,

    allow_origin_regex=r"https://.*\.vercel\.app",

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)

# =====================================================
# ROUTES
# =====================================================

app.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["Dashboard"],
)

app.include_router(
    activity.router,
    prefix="/activity",
    tags=["Activity"],
)

app.include_router(
    upload.router,
    prefix="/upload",
    tags=["Upload"],
)

app.include_router(
    notes.router,
    prefix="/notes",
    tags=["Notes"],
)

app.include_router(
    quiz.router,
    prefix="/quiz",
    tags=["Quiz"],
)

app.include_router(
    chat.router,
    prefix="/chat",
    tags=["Chat"],
)

app.include_router(
    planner.router,
    prefix="/planner",
    tags=["Planner"],
)

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
    }