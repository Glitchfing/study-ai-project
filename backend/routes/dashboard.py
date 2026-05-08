from fastapi import APIRouter

from activity import build_dashboard_payload, record_activity
from models.schemas import DashboardResponse

router = APIRouter()


@router.get("", response_model=DashboardResponse)
def get_dashboard():
    """Return a dashboard derived from user activity."""
    record_activity("dashboard_opened")
    return build_dashboard_payload()

