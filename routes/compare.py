"""Comparison routes for side-by-side election system analysis.

The blueprint turns the static country dataset into a normalized comparison
payload that can be rendered in tables or charts.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from routes.elections import _load_elections_data
from services.exceptions import ValidationError
from services.security_service import get_security_service

logger = logging.getLogger(__name__)

compare_bp = Blueprint("compare", __name__)
limiter = Limiter(key_func=get_remote_address)
security_service = get_security_service()


def _error_response(message: str, status_code: int) -> tuple[dict[str, Any], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


def _cache_bucket() -> int:
    """Return the current hourly cache bucket."""

    return int(time.time() // config.CACHE_TTL_SECONDS)


@lru_cache(maxsize=8)
def _get_metric_catalog(_: int) -> list[dict[str, str]]:
    """Return the static comparison metric catalog."""

    return [
        {"metric": "system_type", "description": "Core constitutional or parliamentary structure."},
        {"metric": "voting_method", "description": "How ballots are cast and counted."},
        {"metric": "election_frequency", "description": "How often major elections occur."},
        {"metric": "governing_body", "description": "Institution responsible for administering elections."},
        {"metric": "voter_eligibility", "description": "Who may vote and under what age rules."},
        {"metric": "compulsory_voting", "description": "Whether voting is legally required."},
        {"metric": "registered_voters", "description": "Approximate size of the electorate."},
        {"metric": "key_features", "description": "High-level distinguishing election features."},
    ]


def _build_voting_method(country_id: str, country_data: dict[str, Any]) -> str:
    """Derive a concise voting method description for a country."""

    method_map = {
        "india": "Electronic voting machine with constituency-based representation",
        "usa": "Federal popular vote with Electoral College certification",
        "uk": "First Past the Post in single-member constituencies",
        "eu": "Proportional representation through member-state lists",
        "brazil": "Two-round presidential voting with electronic ballots",
    }
    return method_map.get(country_id, country_data.get("system", "Election method unavailable"))


def _build_eligibility(country_id: str) -> str:
    """Return a readable voter eligibility summary."""

    eligibility_map = {
        "india": "Indian citizens aged 18+",
        "usa": "Eligible citizens aged 18+ subject to state registration rules",
        "uk": "Eligible UK and qualifying Commonwealth citizens aged 18+",
        "eu": "EU citizens aged 18+ (16+ in some member states)",
        "brazil": "Brazilian citizens aged 16+ with compulsory voting from 18 to 70",
    }
    return eligibility_map.get(country_id, "Eligible voters defined by national law")


def _build_compulsory_voting(country_id: str) -> bool:
    """Return whether voting is compulsory for the given country."""

    return country_id == "brazil"


def _build_key_features(country_data: dict[str, Any]) -> list[str]:
    """Select a short list of key features from the country profile."""

    facts = country_data.get("facts", [])
    features = [country_data.get("description", "")]
    features.extend(facts[:2])
    return [feature for feature in features if feature]


def _build_comparison_entry(country_id: str, country_data: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized comparison entry for one country."""

    return {
        "id": country_id,
        "name": country_data.get("name"),
        "flag": country_data.get("flag"),
        "system_type": country_data.get("system"),
        "voting_method": _build_voting_method(country_id, country_data),
        "election_frequency": country_data.get("frequency"),
        "governing_body": country_data.get("body"),
        "voter_eligibility": _build_eligibility(country_id),
        "compulsory_voting": _build_compulsory_voting(country_id),
        "registered_voters": country_data.get("voters"),
        "key_features": _build_key_features(country_data),
    }


def _build_comparison_payload(country_ids: list[str]) -> dict[str, Any]:
    """Build the comparison payload for the requested countries."""

    elections_data = _load_elections_data()
    entries = []
    for country_id in country_ids:
        country_data = elections_data.get(country_id)
        if not country_data:
            raise ValidationError(f"Country data not found: {country_id}")
        entries.append(_build_comparison_entry(country_id, country_data))

    metrics: dict[str, dict[str, Any]] = {metric: {} for metric in [
        "system_type",
        "voting_method",
        "election_frequency",
        "governing_body",
        "voter_eligibility",
        "compulsory_voting",
        "registered_voters",
        "key_features",
    ]}

    for entry in entries:
        country_id = entry["id"]
        for metric in metrics:
            metrics[metric][country_id] = entry[metric]

    return {
        "countries": entries,
        "comparison": metrics,
    }


@compare_bp.route("/compare", methods=["GET"])
@limiter.limit(f"{config.COMPARE_REQUESTS_PER_MINUTE}/minute")
def compare_countries() -> tuple[dict[str, Any], int]:
    """Compare up to four countries by electoral metrics."""

    countries_param = request.args.get("countries", "")
    if not countries_param:
        return _error_response("Query parameter 'countries' is required", config.HTTP_BAD_REQUEST)

    raw_country_ids = [part.strip() for part in countries_param.split(",") if part.strip()]
    if not raw_country_ids:
        return _error_response("Query parameter 'countries' is required", config.HTTP_BAD_REQUEST)

    if len(raw_country_ids) > config.COMPARE_MAX_COUNTRIES:
        return _error_response("A maximum of four countries may be compared", config.HTTP_BAD_REQUEST)

    try:
        country_ids = [security_service.validate_country_id(country_id) for country_id in raw_country_ids]
        if len(set(country_ids)) != len(country_ids):
            raise ValidationError("Duplicate countries are not allowed")

        payload = _build_comparison_payload(country_ids)
        return jsonify(payload), config.HTTP_OK
    except ValidationError as exc:
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)


@compare_bp.route("/compare/metrics", methods=["GET"])
@limiter.limit(f"{config.COMPARE_REQUESTS_PER_MINUTE}/minute")
def get_compare_metrics() -> tuple[dict[str, Any], int]:
    """Return the available comparison metrics."""

    return jsonify({"metrics": _get_metric_catalog(_cache_bucket())}), config.HTTP_OK