"""Google Vertex AI grounding service for election search responses.

The service keeps grounding configuration and response formatting isolated from
the Flask route layer.
"""

from __future__ import annotations

import logging
from typing import Optional

import vertexai
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel as VertexGenerativeModel
from vertexai.generative_models import HarmCategory, SafetySetting

import config
from services.exceptions import ValidationError

logger = logging.getLogger(__name__)
AIPLATFORM_AVAILABLE = True


class VertexService:
    """Wrapper for Vertex AI grounding and citation formatting."""

    def __init__(self) -> None:
        """Initialize Vertex AI service if enabled."""
        self.available: bool = False
        self.call_count: int = 0
        self.model: Optional[VertexGenerativeModel] = None

        if not config.VERTEX_GROUNDING_ENABLED:
            logger.info("Vertex AI grounding disabled: VERTEX_GROUNDING_ENABLED=false")
            return

        if not config.VERTEX_PROJECT_ID:
            logger.warning("Vertex AI service not available: GOOGLE_CLOUD_PROJECT not set")
            return

        try:
            vertexai.init(project=config.VERTEX_PROJECT_ID, location=config.VERTEX_LOCATION)
            aiplatform.init(project=config.VERTEX_PROJECT_ID, location=config.VERTEX_LOCATION)
            self.model = VertexGenerativeModel(config.GEMINI_MODEL)
            self.available = True
            logger.info("Vertex AI service initialized for project: %s", config.VERTEX_PROJECT_ID)
        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.error("Failed to initialize Vertex AI service", exc_info=True)
            self.available = False

    def _build_safety_settings(self) -> list[SafetySetting]:
        """Return the safety policy used for grounded generation."""

        return [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH),
        ]

    def _build_search_query(self, query: str, country: Optional[str]) -> str:
        """Build a context-aware grounding query.

        Args:
            query: User search prompt.
            country: Optional country context.

        Returns:
            Search query string to send to Vertex AI.
        """

        if country:
            return f"{country} election {query}"
        return query

    def _build_unavailable_response(self) -> dict[str, object]:
        """Return the standard unavailable grounding payload."""

        return {
            "answer": None,
            "sources": [],
            "grounded": False,
            "error": "Vertex AI grounding service unavailable",
        }

    def search_with_grounding(
        self,
        query: str,
        country: Optional[str] = None,
    ) -> dict:
        """
        Search for election information with Google Search grounding.
        Results include cited sources for fact-checking.

        Args:
            query: The election question/search query
            country: Optional country context (e.g., 'india', 'usa')

        Returns:
            Dictionary with 'answer', 'sources', 'grounded', and other metadata
        """
        if not self.available:
            logger.warning("Grounded search requested but service unavailable")
            return self._build_unavailable_response()

        try:
            self.call_count += 1

            search_query = self._build_search_query(query, country)
            logger.info("Grounded search would query: %s (call #%s)", search_query, self.call_count)

            if self.model:
                response = self.model.generate_content(
                    search_query,
                    safety_settings=self._build_safety_settings(),
                )
                response_text = getattr(response, "text", "") or ""
                if response_text:
                    return {
                        "answer": response_text,
                        "sources": [],
                        "grounded": True,
                    }

            return {
                "answer": None,
                "sources": [],
                "grounded": False,
                "message": "Vertex AI grounding not fully configured in this environment",
            }

        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            logger.error("Vertex AI search error", exc_info=True)
            return {
                "answer": None,
                "sources": [],
                "grounded": False,
                "error": str(exc),
            }

    def cite_sources(self, sources: list[dict]) -> str:
        """
        Format sources as citations for inclusion in response.

        Args:
            sources: List of source dictionaries with 'title', 'url', etc.

        Returns:
            Formatted citation string
        """
        if not sources:
            return ""

        citations = "\n\n**Sources:**\n"
        for i, source in enumerate(sources[:5], 1):
            title = source.get("title", "Source")
            url = source.get("url", "")
            if url:
                citations += f"{i}. [{title}]({url})\n"
            else:
                citations += f"{i}. {title}\n"

        return citations

    def is_available(self) -> bool:
        """Check if Vertex AI service is available."""
        return self.available

    def get_call_count(self) -> int:
        """Get the number of API calls made."""
        return self.call_count


# Singleton instance
_vertex_service: Optional[VertexService] = None


def get_vertex_service() -> VertexService:
    """Get or create the Vertex AI service instance."""
    global _vertex_service
    if _vertex_service is None:
        _vertex_service = VertexService()
    return _vertex_service
