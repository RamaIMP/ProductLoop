"""Manufacturer reporting scope; does not change consumer taxonomy or source records."""
from app.models.taxonomy import ISSUE_TYPES

DASHBOARD_ISSUE_TYPES=tuple(issue for issue in ISSUE_TYPES if issue!='shaving_performance')
