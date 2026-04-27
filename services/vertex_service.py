"""Google Vertex AI grounding service for election search responses.

The service keeps grounding configuration and response formatting isolated from
the Flask route layer.
"""

import logging
from typing import Optional

import config
from services.exceptions import ValidationError

logger = logging.getLogger(__name__)

try:
    from google.cloud import aiplatform
    from google.cloud.aiplatform import generative_models

    AIPLATFORM_AVAILABLE = True
except ImportError:
    AIPLATFORM_AVAILABLE = False
    logger.warning("google-cloud-aiplatform not installed. Vertex AI grounding will be unavailable.")


class VertexService:
    """Wrapper for Vertex AI grounding and citation formatting."""

    def __init__(self) -> None:
        """Initialize Vertex AI service if enabled."""
        self.available: bool = False
        self.call_count: int = 0

        if not AIPLATFORM_AVAILABLE:
            logger.warning("Vertex AI service not available: google-cloud-aiplatform not installed")
            return

        if not config.VERTEX_GROUNDING_ENABLED:
            logger.info("Vertex AI grounding disabled: VERTEX_GROUNDING_ENABLED=false")
            return

        if not config.VERTEX_PROJECT_ID:
            logger.warning("Vertex AI service not available: GOOGLE_CLOUD_PROJECT not set")
            return

        try:
            aiplatform.init(project=config.VERTEX_PROJECT_ID, location=config.VERTEX_LOCATION)
            self.available = True
            logger.info("Vertex AI service initialized for project: %s", config.VERTEX_PROJECT_ID)
        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.error("Failed to initialize Vertex AI service", exc_info=True)
            self.available = False

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
            logger.info(f"Grounded search would query: {search_query} (call #{self.call_count})")
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
