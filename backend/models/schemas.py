from pydantic import BaseModel
from typing import Any, List, Optional


class UserInfo(BaseModel):
    name: str
    initials: str
    role: str
    streak: int


class KPI(BaseModel):
    id: str
    icon: str
    label: str
    value: str
    suffix: str
    delta: str
    positive: bool
    link: Optional[str]


class Topic(BaseModel):
    id: str
    name: str
    sub: str
    pct: int
    color: str
    orb_colors: List[int]


class LongTermStats(BaseModel):
    total_activities: str
    longest_streak: str
    active_days: int


class BarDataPoint(BaseModel):
    month: str
    value: int


class RecentQuiz(BaseModel):
    title: str
    score: int
    difficulty: str
    icon: str
    variant: str
    feedback: Optional[str] = None


class Tip(BaseModel):
    icon: str
    title: str
    body: str


class HeatmapCell(BaseModel):
    lvl: str
    tip: str
    date: str


class ActivityEntry(BaseModel):
    kind: str
    timestamp: str
    topic: Optional[str] = None
    view: Optional[str] = None
    filename: Optional[str] = None
    note_id: Optional[str] = None
    format: Optional[str] = None
    score: Optional[int] = None
    total: Optional[int] = None
    message: Optional[str] = None
    task_id: Optional[int] = None
    done: Optional[bool] = None
    session_id: Optional[str] = None
    file_count: Optional[int] = None
    uploaded_files: Optional[List[str]] = None


class WeakTopic(BaseModel):
    topic: str
    count: int


class EmojiHistoryItem(BaseModel):
    attempt_id: Optional[str] = None
    created_at: Optional[str] = None
    score: int
    total: int
    percentage: int
    emoji: Optional[str] = None
    feedback: Optional[str] = None


class DashboardAnalytics(BaseModel):
    total_sessions: int
    uploaded_files_count: int
    quizzes_attempted: int
    highest_score: int
    average_score: float
    weak_topics: List[WeakTopic]
    most_difficult_topics: List[WeakTopic] = []
    diagrams_generated: int = 0
    learning_progress: int
    study_minutes: int
    topics_mastered: int
    emoji_performance_history: List[EmojiHistoryItem]


class DashboardResponse(BaseModel):
    user: UserInfo
    kpis: List[KPI]
    topics: List[Topic]
    long_term_stats: LongTermStats
    bar_chart: List[BarDataPoint]
    recent_quizzes: List[RecentQuiz]
    tips: List[Tip]
    heatmap_weeks: int
    activity_heatmap: List[List[HeatmapCell]]
    recent_activity: List[ActivityEntry]
    analytics: Optional[DashboardAnalytics] = None
