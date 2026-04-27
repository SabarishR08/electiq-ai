"""AI chat routes for election Q&A.

The blueprint validates incoming requests, delegates to services, and returns
stable JSON responses for the front end and tests.
"""

import logging
from typing import Any, Optional

from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import BadRequest

import config
from services.exceptions import ValidationError
from services.firebase_service import get_firebase_service
from services.gemini_service import get_gemini_service
from services.security_service import get_security_service, require_json_fields

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
security_service = get_security_service()


def _sanitize_input(text: str, max_length: int = config.MAX_MESSAGE_LENGTH) -> str:
    """Sanitize user input to prevent XSS and injection attacks.

    Args:
        text: User input text.
        max_length: Maximum allowed length.

    Returns:
        Sanitized text or an empty string when invalid.
    """

    if not text or not isinstance(text, str):
        return ""

    if len(text) > max_length:
        return ""

    try:
        return security_service.sanitize_html(text, max_length)
    except ValidationError:
        return ""


def _error_response(message: str, status_code: int) -> tuple[dict[str, str], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


def _normalize_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize and sanitize chat history payloads."""

    sanitized_history: list[dict[str, Any]] = []
    for message in history:
        if not isinstance(message, dict):
            continue

        role = str(message.get("role", "assistant")).strip().lower()
        if role not in {"user", "assistant"}:
            role = "assistant"

        content = _sanitize_input(str(message.get("content", "")), 1000)
        if content:
            sanitized_history.append({"role": role, "content": content})

    return sanitized_history


def _summarize_history_if_needed(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize older messages when the conversation gets long."""

    if len(history) <= config.CHAT_SUMMARY_TRIGGER_MESSAGES:
        return history

    gemini_service = get_gemini_service()
    older_history = history[:-config.CHAT_SUMMARY_RECENT_MESSAGES]
    recent_history = history[-config.CHAT_SUMMARY_RECENT_MESSAGES:]
    summary = gemini_service.summarize_history(older_history)
    summarized_history = [{"role": "assistant", "content": f"Conversation summary: {summary}"}] if summary else []
    summarized_history.extend(recent_history)
    return summarized_history


def _parse_chat_request() -> tuple[str, list[dict[str, Any]], str, Optional[str]]:
    """Parse and validate the chat request body.

    Returns:
        A tuple containing the message, history, country, and session ID.

    Raises:
        ValidationError: When the payload is missing required fields or is invalid.
        BadRequest: When the request body cannot be decoded as JSON.
    """

    if not request.is_json:
        raise ValidationError(config.ERROR_CONTENT_TYPE_JSON)

    data = request.get_json(force=True)
    if not isinstance(data, dict):
        raise ValidationError(config.ERROR_MESSAGE_REQUIRED)

    user_message = _sanitize_input(str(data.get("message", "")))
    if not user_message:
        raise ValidationError("Message is required and must be 1-500 characters")

    history = data.get("history", [])
    if not isinstance(history, list):
        raise ValidationError("History must be a list")

    history = _normalize_history(history)

    country = str(data.get("country", "")).lower()
    session_id = data.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        raise ValidationError("session_id must be a string")

    return user_message, history, country, session_id


def _save_chat_history(session_id: str, user_message: str, response_text: str) -> None:
    """Persist the chat exchange when Firebase is available."""

    firebase_service = get_firebase_service()
    if firebase_service.is_available():
        firebase_service.save_message(session_id, "user", user_message)
        firebase_service.save_message(session_id, "assistant", response_text)


def _build_country_suggestions(country_id: str) -> list[str]:
    """Build country-specific suggested questions from election data."""

    from routes.elections import _load_elections_data

    country_data = _load_elections_data().get(country_id, {})
    country_name = country_data.get("name", country_id.title())
    body = country_data.get("body", "the election authority")
    system = country_data.get("system", "the electoral system")
    frequency = country_data.get("frequency", "the election schedule")
    facts = country_data.get("facts", [])
    fact_question = facts[0] if facts else f"What is a key fact about {country_name}?"

    return [
        f"How do elections work in {country_name}?",
        f"What role does {body} play in {country_name}?",
        f"Why is {system} used in {country_name}?",
        f"How often are elections held in {country_name}? ({frequency})",
        f"{fact_question}",
    ]


@chat_bp.route("/api/chat", methods=["POST"])
@limiter.limit(f"{config.CHAT_REQUESTS_PER_MINUTE}/minute")
def chat() -> tuple[dict, int]:
    """Generate an AI response to an election question.

    Returns:
        A JSON payload containing the generated response and availability flags.
    """

    try:
        user_message, history, country, session_id = _parse_chat_request()
        gemini_service = get_gemini_service()
        history = _summarize_history_if_needed(history)
        response_text = gemini_service.generate_response(
            user_message=user_message,
            history=history,
            temperature=0.7,
        )

        if not response_text:
            logger.error("Failed to generate response")
            return _error_response(config.ERROR_FAILED_RESPONSE, config.HTTP_INTERNAL_SERVER_ERROR)

        if session_id:
            _save_chat_history(session_id, user_message, response_text)

        logger.info("Chat response generated for user (length: %s)", len(response_text))

        return jsonify({
            "response": response_text,
            "country": country if country else None,
            "gemini_available": gemini_service.is_available(),
        }), config.HTTP_OK

    except ValidationError as exc:
        logger.warning("Chat validation error: %s", exc)
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)
    except (BadRequest, TypeError, ValueError) as exc:
        logger.error("Chat route error", exc_info=True)
        return _error_response(config.ERROR_FAILED_RESPONSE, config.HTTP_INTERNAL_SERVER_ERROR)


@chat_bp.route("/api/chat/feedback", methods=["POST"])
@limiter.limit(f"{config.CHAT_REQUESTS_PER_MINUTE}/minute")
@require_json_fields("session_id", "message_id", "rating")
def chat_feedback() -> tuple[dict[str, Any], int]:
    """Store feedback for a chat response."""

    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id", "")).strip()
    message_id = str(payload.get("message_id", "")).strip()
    rating = payload.get("rating")

    if not session_id or not message_id:
        return _error_response("Invalid feedback identifiers", config.HTTP_BAD_REQUEST)

    if rating not in (-1, 1):
        return _error_response("rating must be 1 or -1", config.HTTP_BAD_REQUEST)

    firebase_service = get_firebase_service()
    if not firebase_service.is_available():
        return _error_response("Feedback storage not available", config.HTTP_SERVICE_UNAVAILABLE)

    if firebase_service.save_feedback(session_id, message_id, int(rating)):
        return jsonify({"saved": True}), config.HTTP_OK

    return _error_response("Failed to store feedback", config.HTTP_INTERNAL_SERVER_ERROR)


@chat_bp.route("/api/chat/suggestions", methods=["GET"])
@limiter.limit(f"{config.CHAT_REQUESTS_PER_MINUTE}/minute")
def chat_suggestions() -> tuple[dict[str, Any], int]:
    """Return country-specific suggested chat questions."""

    country = request.args.get("country", "")
    try:
        country_id = security_service.validate_country_id(country)
    except ValidationError as exc:
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)

    suggestions = _build_country_suggestions(country_id)
    return jsonify({"country": country_id, "suggestions": suggestions[:5]}), config.HTTP_OK


@chat_bp.route("/api/chat/grounded", methods=["POST"])
@limiter.limit(f"{config.CHAT_REQUESTS_PER_MINUTE}/minute")
def chat_grounded() -> tuple[dict, int]:
    """Generate a grounded, fact-checked response using Vertex AI Search."""

    try:
        if not request.is_json:
            raise ValidationError(config.ERROR_CONTENT_TYPE_JSON)

        data = request.get_json(force=True)
        if not isinstance(data, dict):
            raise ValidationError(config.ERROR_MESSAGE_REQUIRED)

        user_message = _sanitize_input(str(data.get("message", "")))
        if not user_message:
            raise ValidationError(config.ERROR_MESSAGE_REQUIRED)

        from services.vertex_service import get_vertex_service

        vertex_service = get_vertex_service()
        result = vertex_service.search_with_grounding(user_message)

        if result.get("error"):
            logger.warning("Grounded search unavailable: %s", result.get("error"))
            return jsonify({
                "grounded": False,
                "message": result.get("error"),
            }), config.HTTP_SERVICE_UNAVAILABLE

        return jsonify(result), config.HTTP_OK

    except ValidationError as exc:
        logger.warning("Grounded chat validation error: %s", exc)
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)
    except (BadRequest, TypeError, ValueError) as exc:
        logger.error("Grounded chat error", exc_info=True)
        return _error_response("Failed to process grounded query", config.HTTP_INTERNAL_SERVER_ERROR)


@chat_bp.route("/api/chat/history/<session_id>", methods=["GET"])
def get_chat_history(session_id: str) -> tuple[dict, int]:
    """Retrieve chat history for a session.

    Args:
        session_id: Unique session identifier.

    Returns:
        JSON payload containing the saved messages for that session.
    """

    try:
        if not session_id or len(session_id) > config.MAX_SESSION_ID_LENGTH:
            raise ValidationError(config.ERROR_INVALID_SESSION_ID)

        firebase_service = get_firebase_service()

        if not firebase_service.is_available():
            logger.warning("Firebase service unavailable for history retrieval")
            return _error_response("Chat history not available", config.HTTP_SERVICE_UNAVAILABLE)

        history = firebase_service.get_session_history(session_id, limit=50)

        return jsonify({
            "session_id": session_id,
            "messages": history,
            "count": len(history),
        }), config.HTTP_OK

    except ValidationError as exc:
        logger.warning("Chat history validation error: %s", exc)
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)
    except (TypeError, ValueError) as exc:
        logger.error("Error retrieving chat history", exc_info=True)
        return _error_response(config.ERROR_FAILED_HISTORY, config.HTTP_INTERNAL_SERVER_ERROR)
