"""Google Gemini AI service wrapper for election chat responses.

The service keeps Gemini initialization, prompt construction, and fallback
selection isolated from the Flask routes that consume it.
"""

import logging
from typing import Any, Optional

from google.generativeai import GenerativeModel
import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory

import config
from services.exceptions import GeminiServiceError

logger = logging.getLogger(__name__)
GENAI_AVAILABLE = True


class GeminiService:
    """Wrapper around the Google Gemini chat model."""

    def __init__(self) -> None:
        """Initialize Gemini service with API key if available."""
        self.available: bool = False
        self.model: Optional[GenerativeModel] = None
        self.call_count: int = 0

        if not config.GEMINI_API_KEY:
            logger.warning("Gemini service not available: GEMINI_API_KEY not set")
            return

        try:
            genai.configure(api_key=config.GEMINI_API_KEY)
            self.model = GenerativeModel(config.GEMINI_MODEL)
            self.available = True
            logger.info("Gemini service initialized with model: %s", config.GEMINI_MODEL)
        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.error("Failed to initialize Gemini service", exc_info=True)
            raise GeminiServiceError("Gemini service initialization failed") from exc

    def _build_safety_settings(self) -> dict[HarmCategory, HarmBlockThreshold]:
        """Return the Gemini safety thresholds used for content generation."""

        return {
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }

    def _build_conversation(self, user_message: str, history: Optional[list[dict[str, Any]]]) -> str:
        """Build the Gemini prompt from system instructions, history, and the new message.

        Args:
            user_message: Current user question.
            history: Recent message history for conversational context.

        Returns:
            A single prompt string ready for Gemini.
        """

        conversation = config.SYSTEM_PROMPT + "\n\n"
        if history:
            for message in history[-config.CHAT_HISTORY_MAX_LENGTH:]:
                role = "User" if message.get("role") == "user" else "Assistant"
                conversation += f"{role}: {message.get('content', '')}\n\n"

        conversation += f"User: {user_message}\nAssistant:"
        return conversation

    def _fallback_response(self, message: str) -> str:
        """Provide a topic-specific fallback response when Gemini is unavailable."""

        msg_lower = message.lower()
        if any(word in msg_lower for word in ["india", "indian", "lok sabha", "eci"]):
            return (
                "🇮🇳 India uses a Parliamentary system. The Election Commission of India (ECI) "
                "oversees elections. Citizens vote for 543 Lok Sabha seats every 5 years using "
                "Electronic Voting Machines (EVMs). The party or coalition with 272+ seats forms the government."
            )

        if any(word in msg_lower for word in ["usa", "united states", "america", "electoral college"]):
            return (
                "🇺🇸 The USA holds Presidential elections every 4 years. Citizens vote for Electors "
                "who form the Electoral College (538 total). A candidate needs 270 electoral votes to win. "
                "Congress elections occur every 2 years."
            )

        if any(word in msg_lower for word in ["uk", "britain", "england", "parliament", "fptp"]):
            return (
                "🇬🇧 The UK uses First Past the Post voting. Citizens elect 650 MPs to the House of Commons. "
                "The leader of the party with most MPs becomes Prime Minister, invited by the Monarch."
            )

        if any(word in msg_lower for word in ["brazil", "brazilian", "tse", "compulsory"]):
            return (
                "🇧🇷 Brazil has compulsory voting for ages 18–70. The President is elected via a two-round "
                "majority system. Brazil pioneered fully electronic voting in 1996."
            )

        if any(word in msg_lower for word in ["eu", "europe", "european parliament", "mep"]):
            return (
                "🇪🇺 EU citizens elect 720 Members of European Parliament (MEPs) every 5 years. "
                "Each of the 27 member states uses proportional representation. "
                "The Parliament co-legislates EU law alongside the Council."
            )

        return (
            "I'm ElectIQ, your election education guide! Ask me about voting systems, timelines, "
            "or the election process in India, USA, UK, EU, Brazil, and more. 🗳️"
        )

    def generate_response(
        self,
        user_message: str,
        history: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate a response using Gemini or the local fallback text.

        Args:
            user_message: The user's question or message.
            history: Previous chat messages for context.
            temperature: Sampling temperature between 0.0 and 1.0.

        Returns:
            The model response, or a deterministic fallback string.
        """

        if not self.available or not self.model:
            return self._fallback_response(user_message)

        try:
            self.call_count += 1
            conversation = self._build_conversation(user_message, history)
            response = self.model.generate_content(
                conversation,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=512,
                ),
                safety_settings=self._build_safety_settings(),
            )
            if response and response.text:
                logger.info("Gemini response generated (call #%s)", self.call_count)
                return response.text.strip()

            logger.warning("Gemini returned empty response")
            return self._fallback_response(user_message)

        except (AttributeError, TypeError, ValueError, GeminiServiceError) as exc:
            logger.error("Gemini API error", exc_info=True)
            return self._fallback_response(user_message)

    def summarize_history(self, history: list[dict[str, Any]]) -> str:
        """Summarize older chat messages for context compression.

        Args:
            history: Conversation history to summarize.

        Returns:
            A concise summary of the provided conversation history.
        """

        if not history:
            return ""

        if not self.available or not self.model:
            recent_messages = [message.get("content", "") for message in history[-3:]]
            return "Summary of earlier discussion: " + " | ".join(filter(None, recent_messages))

        prompt = (
            "Summarize the following election conversation in 3 concise bullet points "
            "focused on the user's intent and the main facts discussed:\n\n"
            + "\n".join(f"{message.get('role', 'user')}: {message.get('content', '')}" for message in history)
        )

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=180,
                ),
                safety_settings=self._build_safety_settings(),
            )
            if response and response.text:
                return response.text.strip()
        except (AttributeError, TypeError, ValueError) as exc:
            logger.error("Gemini summary error", exc_info=True)

        recent_messages = [message.get("content", "") for message in history[-3:]]
        return "Summary of earlier discussion: " + " | ".join(filter(None, recent_messages))

    def is_available(self) -> bool:
        """Check if Gemini service is available."""
        return self.available

    def get_call_count(self) -> int:
        """Get the number of API calls made."""
        return self.call_count


# Singleton instance
_gemini_service: Optional[GeminiService] = None


def get_gemini_service() -> GeminiService:
    """Get or create the Gemini service instance."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
