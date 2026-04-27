"""Glossary routes for election terminology lookup and explanation.

The blueprint serves the shared glossary dataset, adds fuzzy search, and can
ask Gemini to explain terms in the context of a country or use-case.
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Optional

from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from routes.elections import _load_glossary_data
from services.exceptions import ValidationError
from services.gemini_service import get_gemini_service
from services.security_service import get_security_service, require_json_fields

logger = logging.getLogger(__name__)

glossary_bp = Blueprint("glossary", __name__)
limiter = Limiter(key_func=get_remote_address)
security_service = get_security_service()


def _error_response(message: str, status_code: int) -> tuple[dict[str, Any], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


def _slugify(term: str) -> str:
    """Convert a glossary term to a slug."""

    normalized = term.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def _build_glossary_index() -> list[dict[str, Any]]:
    """Return the glossary entries with derived slugs and examples."""

    entries = []
    for term_key, term_data in _load_glossary_data().items():
        term = term_data.get("term", term_key)
        definition = term_data.get("definition", "")
        entries.append({
            "term": term,
            "slug": _slugify(term),
            "definition": definition,
            "example": f"For example, {term.lower()} can be used in an election education context.",
        })
    return entries


def _build_related_terms(target_term: str, glossary_entries: list[dict[str, Any]]) -> list[str]:
    """Compute a small set of related glossary terms."""

    target_tokens = set(re.findall(r"[a-z0-9]+", target_term.lower()))
    scored_terms: list[tuple[float, str]] = []
    for entry in glossary_entries:
        if entry["term"].lower() == target_term.lower():
            continue
        candidate_tokens = set(re.findall(r"[a-z0-9]+", entry["term"].lower()))
        overlap = len(target_tokens & candidate_tokens)
        ratio = difflib.SequenceMatcher(None, target_term.lower(), entry["term"].lower()).ratio()
        score = overlap + ratio
        scored_terms.append((score, entry["term"]))

    scored_terms.sort(key=lambda item: item[0], reverse=True)
    return [term for _, term in scored_terms[:3]]


def _find_entry_by_slug(term_slug: str) -> Optional[dict[str, Any]]:
    """Find a glossary entry by its slug."""

    normalized_slug = term_slug.lower().strip()
    for entry in _build_glossary_index():
        if entry["slug"] == normalized_slug:
            return entry
    return None


def _search_glossary(query: str) -> list[dict[str, Any]]:
    """Search glossary entries by term and definition relevance."""

    normalized_query = query.lower().strip()
    results: list[tuple[float, dict[str, Any]]] = []
    for entry in _build_glossary_index():
        term_ratio = difflib.SequenceMatcher(None, normalized_query, entry["term"].lower()).ratio()
        definition_ratio = difflib.SequenceMatcher(None, normalized_query, entry["definition"].lower()).ratio()
        token_overlap = len(set(normalized_query.split()) & set(re.findall(r"[a-z0-9]+", entry["definition"].lower())))
        score = term_ratio * 0.55 + definition_ratio * 0.25 + token_overlap * 0.2
        if normalized_query in entry["term"].lower() or normalized_query in entry["definition"].lower() or score > 0:
            results.append((score, entry))

    results.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in results[: config.GLOSSARY_SEARCH_LIMIT]]


def _generate_explanation(term: str, context: str, country: Optional[str]) -> str:
    """Generate a contextual explanation for a glossary term."""

    gemini_service = get_gemini_service()
    if gemini_service.is_available():
        prompt = (
            f"Explain the election term '{term}' in the context of {country or 'the provided context'}. "
            f"Context: {context}. Keep it concise and practical."
        )
        explanation = gemini_service.generate_response(prompt, history=None, temperature=0.2)
        if explanation:
            return explanation

    return f"{term} refers to {context.strip() or 'an election concept'} in a practical election setting."


@glossary_bp.route("/glossary", methods=["GET"])
@limiter.limit(f"{config.GLOSSARY_REQUESTS_PER_MINUTE}/minute")
def list_glossary() -> tuple[dict[str, Any], int]:
    """Return all glossary terms."""

    glossary_data = _load_glossary_data()
    return jsonify({"glossary": list(glossary_data.values())}), config.HTTP_OK


@glossary_bp.route("/glossary/<term_slug>", methods=["GET"])
@limiter.limit(f"{config.GLOSSARY_REQUESTS_PER_MINUTE}/minute")
def get_glossary_term(term_slug: str) -> tuple[dict[str, Any], int]:
    """Return a single glossary term by slug."""

    try:
        entry = _find_entry_by_slug(term_slug)
        if entry is None:
            return _error_response("Term not found", config.HTTP_NOT_FOUND)

        related_terms = _build_related_terms(entry["term"], _build_glossary_index())
        return jsonify({
            "term": entry["term"],
            "definition": entry["definition"],
            "example": entry["example"],
            "related_terms": related_terms,
        }), config.HTTP_OK
    except (TypeError, ValueError) as exc:
        logger.error("Failed to fetch glossary term", exc_info=True)
        return _error_response(str(exc), config.HTTP_INTERNAL_SERVER_ERROR)


@glossary_bp.route("/glossary/search", methods=["GET"])
@limiter.limit(f"{config.GLOSSARY_REQUESTS_PER_MINUTE}/minute")
def search_glossary() -> tuple[dict[str, Any], int]:
    """Search glossary entries by query string."""

    query = request.args.get("q", "").strip()
    if not query:
        return _error_response("Query parameter 'q' is required", config.HTTP_BAD_REQUEST)

    results = _search_glossary(query)
    return jsonify({"query": query, "results": results}), config.HTTP_OK


@glossary_bp.route("/glossary/explain", methods=["POST"])
@limiter.limit(f"{config.GLOSSARY_REQUESTS_PER_MINUTE}/minute")
@require_json_fields("term", "context")
def explain_glossary_term() -> tuple[dict[str, Any], int]:
    """Explain a glossary term in context."""

    payload = request.get_json(silent=True) or {}
    term = security_service.sanitize_html(str(payload.get("term", "")), 120)
    context = security_service.sanitize_html(str(payload.get("context", "")), 1000)
    country = payload.get("country")
    if isinstance(country, str) and country.strip():
        country = security_service.validate_country_id(country)
    else:
        country = None

    explanation = _generate_explanation(term, context, country)
    examples = [
        f"{term} in {country or 'election education'} context: {context}",
        f"{term} example: {context[:120]}",
    ]
    return jsonify({
        "term": term,
        "explanation": explanation,
        "examples": examples,
    }), config.HTTP_OK