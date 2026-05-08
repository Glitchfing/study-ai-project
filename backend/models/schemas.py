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
