"""In-memory analytics routes for lightweight usage tracking.

The blueprint records country and event counts in process memory so the app can
surface popular countries without needing an external database.
"""

from __future__ import annotations

import logging
from collections import Counter
from threading import Lock
from typing import Any

from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from services.exceptions import ValidationError
from services.security_service import get_security_service, require_json_fields

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__)
limiter = Limiter(key_func=get_remote_address)
security_service = get_security_service()

_COUNTRY_VIEWS = Counter()
_EVENT_COUNTS = Counter()
_LOCK = Lock()

_TRACKABLE_EVENTS = {"country_view", "quiz_start", "chat_message"}


def _error_response(message: str, status_code: int) -> tuple[dict[str, Any], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


def _record_event(event: str, country: str | None) -> None:
    """Update in-memory analytics counters."""

    with _LOCK:
        _EVENT_COUNTS[event] += 1
        if country:
            _COUNTRY_VIEWS[country] += 1


def _serialize_popular_countries() -> list[dict[str, Any]]:
    """Serialize the most viewed countries for API responses."""

    with _LOCK:
        sorted_countries = _COUNTRY_VIEWS.most_common(config.ANALYTICS_TOP_COUNTRIES_LIMIT)

    return [{"id": country_id, "views": views} for country_id, views in sorted_countries]


@analytics_bp.route("/analytics/popular", methods=["GET"])
@limiter.limit(f"{config.ANALYTICS_REQUESTS_PER_MINUTE}/minute")
def get_popular_countries() -> tuple[dict[str, Any], int]:
    """Return the most frequently viewed countries."""

    return jsonify({"countries": _serialize_popular_countries()}), config.HTTP_OK


@analytics_bp.route("/analytics/track", methods=["POST"])
@limiter.limit(f"{config.ANALYTICS_REQUESTS_PER_MINUTE}/minute")
@require_json_fields("event")
def track_event() -> tuple[dict[str, Any], int]:
    """Track an in-memory analytics event."""

    payload = request.get_json(silent=True) or {}
    event = str(payload.get("event", "")).strip().lower()
    if event not in _TRACKABLE_EVENTS:
        return _error_response("Unsupported analytics event", config.HTTP_BAD_REQUEST)

    country = payload.get("country")
    if isinstance(country, str) and country.strip():
        try:
            country = security_service.validate_country_id(country)
        except ValidationError as exc:
            return _error_response(str(exc), config.HTTP_BAD_REQUEST)
    else:
        country = None

    if event == "country_view" and not country:
        return _error_response("Country is required for country_view events", config.HTTP_BAD_REQUEST)

    _record_event(event, country)
    return jsonify({"tracked": True}), config.HTTP_OK