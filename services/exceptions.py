"""Custom exceptions for ElectIQ service-layer failures.

These exceptions provide a narrow, explicit error surface for route handlers
and service initialization without leaking framework-specific concerns.
"""


class ElectIQError(Exception):
    """Base exception for ElectIQ service and validation errors."""


class GeminiServiceError(ElectIQError):
    """Raised when the Gemini service cannot complete a request."""


class TranslateServiceError(ElectIQError):
    """Raised when the translation service cannot complete a request."""


class FirebaseServiceError(ElectIQError):
    """Raised when the Firebase service cannot complete a request."""


class ValidationError(ElectIQError):
    """Raised when caller input fails validation rules."""