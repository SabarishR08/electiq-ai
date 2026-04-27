"""Translation routes backed by Google Cloud Translate.

The blueprint validates incoming text requests and delegates translation and
language detection to the service layer.
"""

import logging
from typing import Any, Optional

from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import BadRequest

import config
from services.exceptions import ValidationError
from services.translate_service import get_translate_service
from services.security_service import get_security_service, require_json_fields

logger = logging.getLogger(__name__)

translate_bp = Blueprint("translate", __name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
security_service = get_security_service()


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

    try:
        return security_service.sanitize_html(text, max_length)
    except ValidationError:
        return ""


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

    target_lang = security_service.validate_language_code(str(data.get("target_language", "")))

    source_language = data.get("source_language")
    if source_language is not None and not isinstance(source_language, str):
        raise ValidationError("source_language must be a string")

    return text, target_lang, source_language.lower() if isinstance(source_language, str) else None


def _parse_batch_request() -> tuple[list[str], str, Optional[str]]:
    """Parse and validate the batch translation request body."""

    if not request.is_json:
        raise ValidationError(config.ERROR_CONTENT_TYPE_JSON)

    data = request.get_json(force=True)
    if not isinstance(data, dict):
        raise ValidationError(config.ERROR_TRANSLATION_TEXT_REQUIRED)

    texts = data.get("texts", [])
    if not isinstance(texts, list) or not texts:
        raise ValidationError("texts must be a non-empty list")

    if len(texts) > config.BATCH_TRANSLATION_MAX_ITEMS:
        raise ValidationError("Batch translation supports up to 10 texts")

    sanitized_texts = [text for text in (_sanitize_text(str(item)) for item in texts) if text]
    if not sanitized_texts:
        raise ValidationError("At least one valid text is required")

    target_lang = security_service.validate_language_code(str(data.get("target_language", "")))
    source_language = data.get("source_language")
    if source_language is not None and not isinstance(source_language, str):
        raise ValidationError("source_language must be a string")

    return sanitized_texts, target_lang, source_language.lower() if isinstance(source_language, str) else None


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


@translate_bp.route("/translate/batch", methods=["POST"])
@limiter.limit(f"{config.TRANSLATE_REQUESTS_PER_MINUTE}/minute")
@require_json_fields("texts", "target_language")
def translate_batch() -> tuple[dict, int]:
    """Translate a batch of texts to one target language."""

    try:
        texts, target_lang, source_lang = _parse_batch_request()
        translate_service = get_translate_service()

        translations = [
            translate_service.translate_text(text=text, target_language=target_lang, source_language=source_lang)
            for text in texts
        ]

        source_language = translations[0].get("source_language", source_lang or config.DEFAULT_SOURCE_LANGUAGE) if translations else source_lang or config.DEFAULT_SOURCE_LANGUAGE
        return jsonify({
            "translations": translations,
            "source_language": source_language,
            "count": len(translations),
        }), config.HTTP_OK

    except ValidationError as exc:
        logger.warning("Batch translation validation error: %s", exc)
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)


@translate_bp.route("/translate/supported", methods=["GET"])
@limiter.limit(f"{config.TRANSLATE_REQUESTS_PER_MINUTE}/minute")
def get_supported_language_details() -> tuple[dict, int]:
    """Return language codes with display metadata."""

    return jsonify(config.SUPPORTED_LANGUAGE_DETAILS), config.HTTP_OK


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
