"""Celery task package for the execution job center."""
from app.tasks.celery_app import CELERY_AVAILABLE, app

__all__ = ["app", "CELERY_AVAILABLE"]
