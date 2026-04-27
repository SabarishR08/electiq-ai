"""Security utilities for ElectIQ request validation and tracing.

The service centralizes sanitization, injection detection, request ID generation,
and content policy checks so routes can stay focused on response shaping.
"""

from __future__ import annotations

import logging
import re
import uuid
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import bleach
from flask import jsonify, request

import config
from services.exceptions import ValidationError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class SecurityService:
    """Singleton security helper for input validation and tracing."""

    _instance: Optional["SecurityService"] = None

    _INJECTION_PATTERNS = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"\b(select|insert|drop|union|delete|update)\b",
            r"or\s+1\s*=\s*1",
            r"<script",
            r"javascript:",
            r"onerror\s*=",
            r"onload\s*=",
            r"\{\{",
            r"\}\}",
            r"\{%",
            r"%\}",
            r"<%",
            r"\.\./",
            r"\.\\",
            r"%2e%2e",
        ]
    ]
    _PROFANITY_PATTERNS = [re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE) for word in config.PROFANITY_WORDS]
    _PRIVATE_DATA_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in config.PERSONAL_VOTER_PATTERNS]

    def __new__(cls) -> "SecurityService":
        """Return the shared singleton instance."""

        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def sanitize_html(self, text: str, max_length: int) -> str:
        """Remove HTML content and enforce a maximum length.

        Args:
            text: Input text to sanitize.
            max_length: Maximum length allowed after sanitization.

        Returns:
            Sanitized and truncated text.

        Raises:
            ValidationError: If the sanitized text is empty.
        """

        sanitized_text = bleach.clean(text or "", tags=[], strip=True).strip()
        if not sanitized_text:
            raise ValidationError("Invalid text input")

        return sanitized_text[:max_length]

    def validate_country_id(self, country_id: str) -> str:
        """Validate and normalize a country identifier.

        Args:
            country_id: Candidate country identifier.

        Returns:
            Lowercase country identifier.

        Raises:
            ValidationError: If the identifier is not supported.
        """

        normalized_country = (country_id or "").strip().lower()
        if normalized_country not in config.VALID_COUNTRY_IDS:
            raise ValidationError("Invalid country identifier")
        return normalized_country

    def validate_language_code(self, lang_code: str) -> str:
        """Validate and normalize a language code.

        Args:
            lang_code: Candidate language code.

        Returns:
            Lowercase language code.

        Raises:
            ValidationError: If the code is unsupported.
        """

        normalized_code = (lang_code or "").strip().lower()
        if normalized_code not in config.SUPPORTED_LANGUAGES:
            raise ValidationError("Unsupported language code")
        return normalized_code

    def detect_injection(self, text: str) -> bool:
        """Detect common injection patterns in text.

        Args:
            text: Input text to inspect.

        Returns:
            True when a known injection pattern is present.
        """

        candidate = text or ""
        return any(pattern.search(candidate) for pattern in self._INJECTION_PATTERNS)

    def generate_request_id(self) -> str:
        """Generate a request ID for tracing.

        Returns:
            A UUID4 hex string.
        """

        return uuid.uuid4().hex

    def check_content_policy(self, text: str) -> tuple[bool, str]:
        """Check whether the input is allowed by the content policy.

        Args:
            text: User input to review.

        Returns:
            A tuple of (allowed flag, reason).
        """

        candidate = (text or "").strip()
        if not candidate:
            return False, "Empty content"

        if any(pattern.search(candidate) for pattern in self._PRIVATE_DATA_PATTERNS):
            return False, "Requests for personal voter data are not allowed"

        if any(pattern.search(candidate) for pattern in self._PROFANITY_PATTERNS):
            return False, "Profanity is not allowed"

        return True, "Allowed"


def get_security_service() -> SecurityService:
    """Return the shared security service instance.

    Returns:
        The singleton SecurityService.
    """

    return SecurityService()


def require_json_fields(*required_fields: str) -> Callable[[F], F]:
    """Require a set of JSON fields on the incoming request.

    Args:
        *required_fields: Field names that must exist in request.json.

    Returns:
        A decorator that validates the request body before the route runs.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not request.is_json:
                return jsonify({"error": config.ERROR_CONTENT_TYPE_JSON}), config.HTTP_BAD_REQUEST

            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                payload = {}

            missing_fields = [field for field in required_fields if field not in payload]
            if missing_fields:
                return jsonify({
                    "error": config.ERROR_MISSING_REQUIRED_FIELDS,
                    "required": list(required_fields),
                    "missing": missing_fields,
                }), config.HTTP_BAD_REQUEST

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator