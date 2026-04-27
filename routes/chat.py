"""AI chat routes for election Q&A.

The blueprint validates incoming requests, delegates to services, and returns
stable JSON responses for the front end and tests.
"""

import logging
from typing import Any, Optional

import bleach
from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import BadRequest

import config
from services.exceptions import ValidationError
from services.firebase_service import get_firebase_service
from services.gemini_service import get_gemini_service

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


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

    cleaned_text = text.strip()
    if len(cleaned_text) < config.MIN_MESSAGE_LENGTH or len(cleaned_text) > max_length:
        return ""

    return bleach.clean(cleaned_text, tags=[], strip=True)


def _error_response(message: str, status_code: int) -> tuple[dict[str, str], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


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
