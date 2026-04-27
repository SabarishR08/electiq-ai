"""Google Cloud Translate service wrapper for language utilities.

The service encapsulates translation, detection, and validation so routes only
coordinate request parsing and response shaping.
"""

import logging
from typing import Any, Optional

import config
from services.exceptions import TranslateServiceError, ValidationError

logger = logging.getLogger(__name__)

try:
    from google.cloud import translate_v2 as translate
    TRANSLATE_AVAILABLE = True
except ImportError:
    TRANSLATE_AVAILABLE = False
    logger.warning("google-cloud-translate not installed. Translation will be unavailable.")


class TranslateService:
    """Wrapper around Google Cloud Translate v2 API calls."""

    def __init__(self) -> None:
        """Initialize translation service if enabled."""
        self.available: bool = False
        self.client = None
        self.call_count: int = 0

        if not TRANSLATE_AVAILABLE:
            logger.warning("Translate service not available: google-cloud-translate not installed")
            return

        if not config.TRANSLATE_ENABLED:
            logger.info("Translate service disabled: GOOGLE_TRANSLATE_ENABLED=false")
            return

        try:
            self.client = translate.Client()
            self.available = True
            logger.info("Translate service initialized successfully")
        except (AttributeError, RuntimeError, ValueError, OSError) as exc:
            logger.error("Failed to initialize Translate service", exc_info=True)
            raise TranslateServiceError("Translate service initialization failed") from exc

    def _build_error_result(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str],
        error_message: str,
    ) -> dict[str, str]:
        """Build a consistent translation error payload.

        Args:
            text: Original text passed by the caller.
            target_language: Target language code.
            source_language: Optional source language code.
            error_message: Error message to include.

        Returns:
            A response-shaped error dictionary.
        """

        return {
            "translated_text": text,
            "source_language": source_language or config.DEFAULT_SOURCE_LANGUAGE,
            "target_language": target_language,
            "error": error_message,
        }

    def _validate_translation_request(self, text: str, target_language: str) -> None:
        """Validate translation inputs before calling the API.

        Args:
            text: Text to translate.
            target_language: Requested target language.

        Raises:
            ValidationError: If any input fails validation.
        """

        if not text or not text.strip():
            raise ValidationError("Empty text")

        if len(text) > config.MAX_TEXT_TRANSLATION_LENGTH:
            raise ValidationError("Text too long")

        if target_language not in config.SUPPORTED_LANGUAGES:
            raise ValidationError(f"Language {target_language} not supported")

    def _translate_via_client(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str],
    ) -> dict[str, str]:
        """Translate text through the configured Google client.

        Args:
            text: Text to translate.
            target_language: Target language code.
            source_language: Optional source language code.

        Returns:
            Standardized translation result.
        """

        result = self.client.translate(  # type: ignore[union-attr]
            text,
            target_language=target_language,
            source_language=source_language,
        )
        translated = result.get("translatedText", text)
        detected_source = result.get("detectedSourceLanguage", source_language or config.DEFAULT_SOURCE_LANGUAGE)
        logger.info("Translation completed: %s -> %s (call #%s)", detected_source, target_language, self.call_count)
        return {
            "translated_text": translated,
            "source_language": detected_source,
            "target_language": target_language,
        }

    def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> dict:
        """
        Translate text to target language.

        Args:
            text: Text to translate
            target_language: Target language code (e.g., 'es', 'fr', 'hi')
            source_language: Source language code (optional, auto-detected if not provided)

        Returns:
            Dictionary with 'translated_text', 'source_language', and 'target_language'
        """
        if not self.available or not self.client:
            logger.warning("Translation requested but service unavailable for: %s", target_language)
            return self._build_error_result(text, target_language, source_language, "Translation service unavailable")

        try:
            self._validate_translation_request(text, target_language)
        except ValidationError as exc:
            return self._build_error_result(text, target_language, source_language, str(exc))

        try:
            self.call_count += 1
            return self._translate_via_client(text, target_language, source_language)
        except (AttributeError, KeyError, TypeError, ValueError, TranslateServiceError) as exc:
            logger.error("Translation error", exc_info=True)
            return self._build_error_result(text, target_language, source_language, str(exc))

    def detect_language(self, text: str) -> str:
        """
        Detect the language of given text.

        Args:
            text: Text to detect language for

        Returns:
            Language code (e.g., 'en', 'es', 'hi')
        """
        if not self.available or not self.client:
            logger.warning("Language detection requested but service unavailable")
            return config.DEFAULT_SOURCE_LANGUAGE

        if not text or not text.strip():
            return config.DEFAULT_SOURCE_LANGUAGE

        try:
            result = self.client.detect_language(text)
            language = result.get("language", config.DEFAULT_SOURCE_LANGUAGE)
            logger.debug("Detected language: %s", language)
            return language
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            logger.error("Language detection error", exc_info=True)
            return config.DEFAULT_SOURCE_LANGUAGE

    def is_available(self) -> bool:
        """Check if translation service is available."""
        return self.available

    def get_call_count(self) -> int:
        """Get the number of API calls made."""
        return self.call_count

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages."""
        return config.SUPPORTED_LANGUAGES.copy()


# Singleton instance
_translate_service: Optional[TranslateService] = None


def get_translate_service() -> TranslateService:
    """Get or create the Translate service instance."""
    global _translate_service
    if _translate_service is None:
        _translate_service = TranslateService()
    return _translate_service
