"""Election data routes for country information, timelines, and glossary.

The blueprint serves data loaded from JSON files and keeps the request/response
layer separate from the data loading helpers.
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Any

from flask import Blueprint, jsonify, request

import config
from services.exceptions import ValidationError
from services.security_service import get_security_service

logger = logging.getLogger(__name__)

elections_bp = Blueprint("elections", __name__)
security_service = get_security_service()


def _load_json_file(file_path: str) -> dict[str, Any]:
    """Load and parse a JSON file from disk.

    Args:
        file_path: Absolute path to the JSON file.

    Returns:
        Parsed JSON document or an empty dictionary on failure.
    """

    try:
        with open(file_path, "r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        logger.error("Failed to load JSON file: %s", file_path, exc_info=True)
        return {}


def _build_country_summary(country_data: dict[str, Any]) -> dict[str, Any]:
    """Build the compact country summary used by the landing page."""

    return {
        "name": country_data.get("name"),
        "flag": country_data.get("flag"),
        "system": country_data.get("system"),
        "color": country_data.get("color"),
        "voters": country_data.get("voters"),
        "body": country_data.get("body"),
    }


def _cache_bucket() -> int:
    """Return the current hourly cache bucket."""

    return int(time.time() // config.CACHE_TTL_SECONDS)


@lru_cache(maxsize=4)
def _get_cached_elections_data(cache_key: int) -> dict[str, Any]:
    """Return cached elections data for the current hour bucket."""

    del cache_key
    return _load_json_file(config.ELECTIONS_DATA_FILE)


@lru_cache(maxsize=4)
def _get_cached_glossary_data(cache_key: int) -> dict[str, Any]:
    """Return cached glossary data for the current hour bucket."""

    del cache_key
    glossary_data = _load_json_file(config.GLOSSARY_DATA_FILE)
    return {term["term"].lower(): term for term in glossary_data.get("glossary", []) if term.get("term")}


def _load_elections_data() -> dict[str, Any]:
    """Load elections data from the JSON fixture."""

    data = _get_cached_elections_data(_cache_bucket())
    logger.info("Loaded elections data with %s countries", len(data))
    return data


def _load_glossary_data() -> dict[str, Any]:
    """Load glossary data from the JSON fixture."""

    data = _get_cached_glossary_data(_cache_bucket())
    logger.info("Loaded glossary with %s terms", len(data))
    return data


def _error_response(message: str, status_code: int) -> tuple[dict[str, str], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


def _build_estimated_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach estimated time metadata to voting steps."""

    estimated_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps, 1):
        enriched_step = dict(step)
        enriched_step["estimated_minutes"] = index + config.STATIC_ESTIMATED_STEP_MINUTES
        estimated_steps.append(enriched_step)
    return estimated_steps


def _score_country(country_id: str, country_data: dict[str, Any], query: str) -> float:
    """Score a country against a search query."""

    haystack = " ".join([
        country_data.get("name", ""),
        country_data.get("system", ""),
        country_data.get("description", ""),
        " ".join(country_data.get("facts", [])),
    ]).lower()
    tokens = query.lower().split()
    score = sum(token in haystack for token in tokens)
    if country_id in query.lower():
        score += 2
    return float(score)


@elections_bp.route("/api/elections", methods=["GET"])
def get_all_elections() -> tuple[dict, int]:
    """Get summary information for all supported countries."""

    try:
        data = _load_elections_data()
        summary = {country_id: _build_country_summary(country_data) for country_id, country_data in data.items()}
        return jsonify(summary), config.HTTP_OK
    except (TypeError, ValueError):
        logger.error("Error fetching elections", exc_info=True)
        return _error_response("Failed to fetch elections data", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/elections/search", methods=["GET"])
def search_elections() -> tuple[dict, int]:
    """Search countries by description, facts, and system type."""

    query = request.args.get("q", "").strip()
    if not query:
        return _error_response("Query parameter 'q' is required", config.HTTP_BAD_REQUEST)

    elections_data = _load_elections_data()
    results = []
    for country_id, country_data in elections_data.items():
        score = _score_country(country_id, country_data, query)
        if score > 0:
            results.append({
                "id": country_id,
                "name": country_data.get("name"),
                "score": score,
                "system": country_data.get("system"),
            })

    results.sort(key=lambda item: item["score"], reverse=True)
    return jsonify({"query": query, "results": results[: config.API_SEARCH_MAX_RESULTS]}), config.HTTP_OK


@elections_bp.route("/api/elections/<country_id>", methods=["GET"])
def get_election_details(country_id: str) -> tuple[dict, int]:
    """Get full election details for a country."""

    try:
        normalized_country = security_service.validate_country_id(country_id)
        data = _load_elections_data()
        country_data = data.get(normalized_country)

        if not country_data:
            return _error_response("Country data not found", config.HTTP_NOT_FOUND)

        return jsonify(country_data), config.HTTP_OK
    except ValidationError:
        return _error_response(config.ERROR_COUNTRY_NOT_FOUND, config.HTTP_NOT_FOUND)
    except (TypeError, ValueError):
        logger.error("Error fetching election details for %s", country_id, exc_info=True)
        return _error_response("Failed to fetch election data", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/elections/<country_id>/timeline", methods=["GET"])
def get_election_timeline(country_id: str) -> tuple[dict, int]:
    """Get election timeline for a country."""

    try:
        normalized_country = security_service.validate_country_id(country_id)
        data = _load_elections_data()
        country_data = data.get(normalized_country, {})
        timeline = country_data.get("timeline", [])

        if not timeline:
            logger.warning("No timeline found for %s", normalized_country)
            return _error_response("Timeline not found", config.HTTP_NOT_FOUND)

        return jsonify({
            "country": normalized_country,
            "country_name": country_data.get("name"),
            "timeline": timeline,
        }), config.HTTP_OK
    except ValidationError:
        return _error_response(config.ERROR_COUNTRY_NOT_FOUND, config.HTTP_NOT_FOUND)
    except (TypeError, ValueError):
        logger.error("Error fetching timeline for %s", country_id, exc_info=True)
        return _error_response("Failed to fetch timeline", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/elections/<country_id>/voting-steps", methods=["GET"])
def get_voting_steps(country_id: str) -> tuple[dict, int]:
    """Get the voting steps for a country."""

    try:
        normalized_country = security_service.validate_country_id(country_id)
        data = _load_elections_data()
        country_data = data.get(normalized_country, {})
        steps = country_data.get("steps", [])

        if not steps:
            logger.warning("No voting steps found for %s", normalized_country)
            return _error_response("Voting steps not found", config.HTTP_NOT_FOUND)

        return jsonify({
            "country": normalized_country,
            "country_name": country_data.get("name"),
            "steps": _build_estimated_steps(steps),
        }), config.HTTP_OK
    except ValidationError:
        return _error_response(config.ERROR_COUNTRY_NOT_FOUND, config.HTTP_NOT_FOUND)
    except (TypeError, ValueError):
        logger.error("Error fetching voting steps for %s", country_id, exc_info=True)
        return _error_response("Failed to fetch voting steps", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/elections/<country_id>/facts", methods=["GET"])
def get_country_facts(country_id: str) -> tuple[dict, int]:
    """Return all facts for a country."""

    try:
        normalized_country = security_service.validate_country_id(country_id)
        data = _load_elections_data()
        country_data = data.get(normalized_country, {})
        facts = country_data.get("facts", [])
        if not facts:
            return _error_response("Facts not found", config.HTTP_NOT_FOUND)
        return jsonify({"country": normalized_country, "facts": facts}), config.HTTP_OK
    except ValidationError:
        return _error_response(config.ERROR_COUNTRY_NOT_FOUND, config.HTTP_NOT_FOUND)


