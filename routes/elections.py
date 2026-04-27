"""Election data routes for country information, timelines, and glossary.

The blueprint serves data loaded from JSON files and keeps the request/response
layer separate from the data loading helpers.
"""

import json
import logging
from typing import Any, Optional

from flask import Blueprint, jsonify

import config

logger = logging.getLogger(__name__)

elections_bp = Blueprint("elections", __name__)

# Cache for elections data
_elections_cache: Optional[dict[str, Any]] = None
_glossary_cache: Optional[dict[str, Any]] = None


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
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
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


def _load_elections_data() -> dict[str, Any]:
    """Load elections data from the JSON fixture."""

    global _elections_cache
    if _elections_cache is not None:
        return _elections_cache

    _elections_cache = _load_json_file(config.ELECTIONS_DATA_FILE)
    logger.info("Loaded elections data with %s countries", len(_elections_cache))
    return _elections_cache


def _load_glossary_data() -> dict[str, Any]:
    """Load glossary data from the JSON fixture."""

    global _glossary_cache
    if _glossary_cache is not None:
        return _glossary_cache

    glossary_data = _load_json_file(config.GLOSSARY_DATA_FILE)
    _glossary_cache = {term["term"].lower(): term for term in glossary_data.get("glossary", []) if term.get("term")}
    logger.info("Loaded glossary with %s terms", len(_glossary_cache))
    return _glossary_cache


def _error_response(message: str, status_code: int) -> tuple[dict[str, str], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


@elections_bp.route("/api/elections", methods=["GET"])
def get_all_elections() -> tuple[dict, int]:
    """Get summary information for all supported countries."""

    try:
        data = _load_elections_data()
        summary = {country_id: _build_country_summary(country_data) for country_id, country_data in data.items()}
        return jsonify(summary), config.HTTP_OK
    except (TypeError, ValueError) as exc:
        logger.error("Error fetching elections", exc_info=True)
        return _error_response("Failed to fetch elections data", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/elections/<country_id>", methods=["GET"])
def get_election_details(country_id: str) -> tuple[dict, int]:
    """Get full election details for a country."""

    country_id = country_id.lower()

    if country_id not in config.ALLOWED_COUNTRIES:
        logger.warning("Invalid country requested: %s", country_id)
        return _error_response(config.ERROR_COUNTRY_NOT_FOUND, config.HTTP_NOT_FOUND)

    try:
        data = _load_elections_data()
        country_data = data.get(country_id)

        if not country_data:
            return _error_response("Country data not found", config.HTTP_NOT_FOUND)

        return jsonify(country_data), config.HTTP_OK
    except (TypeError, ValueError) as exc:
        logger.error("Error fetching election details for %s", country_id, exc_info=True)
        return _error_response("Failed to fetch election data", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/elections/<country_id>/timeline", methods=["GET"])
def get_election_timeline(country_id: str) -> tuple[dict, int]:
    """Get election timeline for a country."""

    country_id = country_id.lower()

    if country_id not in config.ALLOWED_COUNTRIES:
        return _error_response(config.ERROR_COUNTRY_NOT_FOUND, config.HTTP_NOT_FOUND)

    try:
        data = _load_elections_data()
        country_data = data.get(country_id, {})
        timeline = country_data.get("timeline", [])

        if not timeline:
            logger.warning("No timeline found for %s", country_id)
            return _error_response("Timeline not found", config.HTTP_NOT_FOUND)

        return jsonify({
            "country": country_id,
            "country_name": country_data.get("name"),
            "timeline": timeline,
        }), config.HTTP_OK
    except (TypeError, ValueError) as exc:
        logger.error("Error fetching timeline for %s", country_id, exc_info=True)
        return _error_response("Failed to fetch timeline", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/elections/<country_id>/voting-steps", methods=["GET"])
def get_voting_steps(country_id: str) -> tuple[dict, int]:
    """Get the voting steps for a country."""

    country_id = country_id.lower()

    if country_id not in config.ALLOWED_COUNTRIES:
        return _error_response(config.ERROR_COUNTRY_NOT_FOUND, config.HTTP_NOT_FOUND)

    try:
        data = _load_elections_data()
        country_data = data.get(country_id, {})
        steps = country_data.get("steps", [])

        if not steps:
            logger.warning("No voting steps found for %s", country_id)
            return _error_response("Voting steps not found", config.HTTP_NOT_FOUND)

        return jsonify({
            "country": country_id,
            "country_name": country_data.get("name"),
            "steps": steps,
        }), config.HTTP_OK
    except (TypeError, ValueError) as exc:
        logger.error("Error fetching voting steps for %s", country_id, exc_info=True)
        return _error_response("Failed to fetch voting steps", config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/glossary", methods=["GET"])
def get_glossary() -> tuple[dict, int]:
    """Get the election terminology glossary."""

    try:
        data = _load_json_file(config.GLOSSARY_DATA_FILE)
        return jsonify(data), config.HTTP_OK
    except (TypeError, ValueError) as exc:
        logger.error("Error fetching glossary", exc_info=True)
        return _error_response(config.ERROR_FAILED_GLOSSARY, config.HTTP_INTERNAL_SERVER_ERROR)


@elections_bp.route("/api/glossary/<term>", methods=["GET"])
def get_glossary_term(term: str) -> tuple[dict, int]:
    """Get a definition for a specific glossary term."""

    term_lower = term.lower()

    try:
        glossary = _load_glossary_data()

        if term_lower not in glossary:
            logger.warning("Glossary term not found: %s", term)
            return _error_response("Term not found", config.HTTP_NOT_FOUND)

        return jsonify(glossary[term_lower]), config.HTTP_OK
    except (TypeError, ValueError) as exc:
        logger.error("Error fetching glossary term %s", term, exc_info=True)
        return _error_response("Failed to fetch term", config.HTTP_INTERNAL_SERVER_ERROR)
