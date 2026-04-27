"""Translation routes backed by Google Cloud Translate.

The blueprint validates incoming text requests and delegates translation and
language detection to the service layer.
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
from services.translate_service import get_translate_service

logger = logging.getLogger(__name__)

translate_bp = Blueprint("translate", __name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


def _sanitize_text(text: str, max_length: int = config.MAX_TEXT_TRANSLATION_LENGTH) -> str:
    """Sanitize text for translation.

    Args:
        text: Text to sanitize.
        max_length: Maximum allowed length.

    Returns:
        Sanitized text or an empty string if invalid.
    """

    if not text or not isinstance(text, str):
        return ""

    cleaned_text = text.strip()
    if len(cleaned_text) == 0 or len(cleaned_text) > max_length:
        return ""

    return bleach.clean(cleaned_text, tags=[], strip=True)


def _error_response(message: str, status_code: int) -> tuple[dict[str, str], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


def _parse_translate_request() -> tuple[str, str, Optional[str]]:
    """Parse and validate the translation request body.

    Returns:
        The sanitized text, target language, and optional source language.

    Raises:
        ValidationError: If the payload is missing required fields or is invalid.
        BadRequest: When the request body cannot be decoded as JSON.
    """

    if not request.is_json:
        raise ValidationError(config.ERROR_CONTENT_TYPE_JSON)

    data = request.get_json(force=True)
    if not isinstance(data, dict):
        raise ValidationError(config.ERROR_TRANSLATION_TEXT_REQUIRED)

    text = _sanitize_text(str(data.get("text", "")))
    if not text:
        raise ValidationError("Text is required (1-5000 characters)")

    target_lang = str(data.get("target_language", "")).lower()
    if not target_lang or len(target_lang) != 2:
        raise ValidationError("Valid target_language required (e.g., 'es', 'fr', 'hi')")

    source_language = data.get("source_language")
    if source_language is not None and not isinstance(source_language, str):
        raise ValidationError("source_language must be a string")

    return text, target_lang, source_language.lower() if isinstance(source_language, str) else None


@translate_bp.route("/api/translate", methods=["POST"])
@limiter.limit(f"{config.TRANSLATE_REQUESTS_PER_MINUTE}/minute")
def translate_text() -> tuple[dict, int]:
    """Translate text to the requested language.

    Returns:
        A JSON payload with translated text or a structured error.
    """

    try:
        text, target_lang, source_lang = _parse_translate_request()
        translate_service = get_translate_service()

        if not translate_service.is_available():
            logger.warning("Translation service unavailable")
            return jsonify({
                "error": "Translation service not available",
                "text": text,
            }), config.HTTP_SERVICE_UNAVAILABLE

        result = translate_service.translate_text(
            text=text,
            target_language=target_lang,
            source_language=source_lang,
        )

        if result.get("error"):
            logger.warning("Translation error: %s", result.get("error"))
            return jsonify(result), config.HTTP_BAD_REQUEST

        logger.info("Translation completed: %s -> %s", result.get("source_language"), result.get("target_language"))

        return jsonify(result), config.HTTP_OK

    except ValidationError as exc:
        logger.warning("Translation validation error: %s", exc)
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)
    except (BadRequest, TypeError, ValueError) as exc:
        logger.error("Translation route error", exc_info=True)
        return _error_response(config.ERROR_FAILED_TRANSLATION, config.HTTP_INTERNAL_SERVER_ERROR)


@translate_bp.route("/api/translate/detect", methods=["POST"])
@limiter.limit(f"{config.TRANSLATE_REQUESTS_PER_MINUTE}/minute")
def detect_language() -> tuple[dict, int]:
    """Detect the language of the given text.

    Returns:
        A JSON payload with the detected language code.
    """

    try:
        if not request.is_json:
            raise ValidationError(config.ERROR_CONTENT_TYPE_JSON)

        data = request.get_json(force=True)
        if not isinstance(data, dict):
            raise ValidationError(config.ERROR_TRANSLATION_TEXT_REQUIRED)

        text = _sanitize_text(str(data.get("text", "")))
        if not text:
            raise ValidationError("Text is required")

        translate_service = get_translate_service()

        if not translate_service.is_available():
            logger.warning("Translation service unavailable for language detection")
            return _error_response("Translation service not available", config.HTTP_SERVICE_UNAVAILABLE)

        detected_lang = translate_service.detect_language(text)

        return jsonify({
            "text": text,
            "detected_language": detected_lang,
        }), config.HTTP_OK

    except ValidationError as exc:
        logger.warning("Language detection validation error: %s", exc)
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)
    except (BadRequest, TypeError, ValueError) as exc:
        logger.error("Language detection error", exc_info=True)
        return _error_response(config.ERROR_FAILED_LANGUAGE_DETECTION, config.HTTP_INTERNAL_SERVER_ERROR)


@translate_bp.route("/api/languages", methods=["GET"])
def get_supported_languages() -> tuple[dict, int]:
    """Return the supported translation languages.

    Returns:
        A JSON payload containing supported language codes.
    """

    try:
        translate_service = get_translate_service()
        languages = translate_service.get_supported_languages()

        return jsonify({
            "supported_languages": languages,
            "count": len(languages),
        }), config.HTTP_OK

    except (AttributeError, TypeError, ValueError) as exc:
        logger.error("Error fetching supported languages", exc_info=True)
        return _error_response("Failed to fetch language list", config.HTTP_INTERNAL_SERVER_ERROR)
