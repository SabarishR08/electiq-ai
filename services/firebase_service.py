"""Firebase / Firestore service for chat session persistence.

The service encapsulates initialization, message storage, history retrieval,
and session deletion behind a small API used by the Flask routes.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import firebase_admin
from firebase_admin import auth, credentials, firestore
from google.cloud import firestore as google_firestore

import config
from services.exceptions import FirebaseServiceError, ValidationError

logger = logging.getLogger(__name__)
FIREBASE_AVAILABLE = True


class FirebaseService:
    """Wrapper around Firebase Admin SDK and Firestore."""

    def __init__(self) -> None:
        """Initialize Firebase service if enabled."""
        self.available: bool = False
        self.db: Optional[google_firestore.Client] = None
        self.call_count: int = 0

        if not config.FIREBASE_ENABLED:
            logger.info("Firebase service disabled: FIREBASE_ENABLED=false")
            return

        try:
            self._initialize_app()
            self.db = firestore.client()
            self.available = True
            logger.info("Firebase service initialized successfully")
        except (AttributeError, RuntimeError, ValueError, FirebaseServiceError) as exc:
            logger.error("Failed to initialize Firebase service", exc_info=True)
            self.available = False

    def _initialize_app(self) -> Any:
        """Initialize the Firebase Admin app if it is not already configured.

        Returns:
            The initialized or existing Firebase app object.

        Raises:
            FirebaseServiceError: If initialization cannot be completed.
        """

        try:
            return firebase_admin.get_app()
        except ValueError:
            if config.FIREBASE_CREDENTIALS_PATH:
                cred = credentials.Certificate(config.FIREBASE_CREDENTIALS_PATH)
                return firebase_admin.initialize_app(cred)

            return firebase_admin.initialize_app()

    def _build_message_payload(
        self,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a Firestore message payload."""

        return {
            "role": role,
            "content": content,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "metadata": metadata or {},
        }

    def _get_session_reference(self, session_id: str) -> Any:
        """Return the Firestore session document reference."""

        return self.db.collection(config.FIRESTORE_CHAT_COLLECTION).document(session_id)

    def save_session(self, session_id: str, payload: dict[str, Any]) -> bool:
        """Persist top-level session metadata in Firestore."""

        if not self.available or not self.db:
            logger.warning("Save session requested but Firebase unavailable")
            return False

        try:
            self._validate_session_input(session_id)
            session_ref = self._get_session_reference(session_id)
            payload_to_store = dict(payload)
            payload_to_store.setdefault("created_at", google_firestore.SERVER_TIMESTAMP)
            payload_to_store["updated_at"] = google_firestore.SERVER_TIMESTAMP
            session_ref.set(payload_to_store, merge=True)
            return True
        except (AttributeError, RuntimeError, ValueError, ValidationError) as exc:
            logger.error("Error saving session", exc_info=True)
            return False

    def get_session(self, session_id: str) -> dict[str, Any]:
        """Return stored session metadata and messages for a session."""

        if not self.available or not self.db:
            return {}

        try:
            self._validate_session_input(session_id)
            session_ref = self._get_session_reference(session_id)
            session_snapshot = session_ref.get()
            session_data = session_snapshot.to_dict() if session_snapshot.exists else {}
            session_data["messages"] = self.get_session_history(session_id)
            return session_data
        except (AttributeError, RuntimeError, ValueError, ValidationError) as exc:
            logger.error("Error retrieving session", exc_info=True)
            return {}

    def _validate_session_input(self, session_id: str, role: Optional[str] = None, content: Optional[str] = None) -> None:
        """Validate Firestore session inputs.

        Raises:
            ValidationError: If any input is empty.
        """

        if not session_id:
            raise ValidationError("Invalid session_id")

        if role is not None and not role:
            raise ValidationError("Invalid role")

        if content is not None and not content:
            raise ValidationError("Invalid content")

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Save a chat message to Firestore.

        Args:
            session_id: Unique session identifier
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata dict

        Returns:
            True if successful, False otherwise
        """
        if not self.available or not self.db:
            logger.warning("Save message requested but Firebase unavailable")
            return False

        try:
            self._validate_session_input(session_id, role, content)
        except ValidationError as exc:
            logger.warning("Invalid message parameters: %s", exc)
            return False

        try:
            self.call_count += 1
            session_ref = self._get_session_reference(session_id)
            session_ref.set(
                {
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "ttl": firestore.SERVER_TIMESTAMP,
                    "message_count": firestore.Increment(1),
                },
                merge=True,
            )
            session_ref.collection("messages").add(self._build_message_payload(role, content, metadata))
            logger.info("Message saved to session %s (call #%s)", session_id, self.call_count)
            return True

        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.error("Error saving message", exc_info=True)
            return False

    def get_session_history(self, session_id: str, limit: int = 20) -> list[dict]:
        """
        Retrieve chat history for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of messages to retrieve

        Returns:
            List of message dictionaries
        """
        if not self.available or not self.db:
            logger.warning("Get history requested but Firebase unavailable")
            return []

        try:
            self._validate_session_input(session_id)
        except ValidationError as exc:
            logger.warning("Invalid session_id: %s", exc)
            return []

        try:
            self.call_count += 1

            messages_ref = (
                self._get_session_reference(session_id)
                .collection("messages")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )

            docs = messages_ref.stream()
            history: list[dict[str, Any]] = []

            for doc in docs:
                data = doc.to_dict()
                history.insert(
                    0,
                    {
                        "id": doc.id,
                        "role": data.get("role"),
                        "content": data.get("content"),
                        "timestamp": data.get("timestamp"),
                    },
                )

            logger.info("Retrieved %s messages from session %s", len(history), session_id)
            return history

        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.error("Error retrieving history", exc_info=True)
            return []

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a chat session and all its messages.

        Args:
            session_id: Session identifier

        Returns:
            True if successful, False otherwise
        """
        if not self.available or not self.db:
            logger.warning("Delete session requested but Firebase unavailable")
            return False

        try:
            self._validate_session_input(session_id)
        except ValidationError as exc:
            logger.warning("Invalid session_id: %s", exc)
            return False

        try:
            self.call_count += 1
            session_ref = self._get_session_reference(session_id)
            messages = session_ref.collection("messages").stream()
            for msg in messages:
                msg.reference.delete()

            session_ref.delete()

            logger.info("Session %s deleted", session_id)
            return True

        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.error("Error deleting session", exc_info=True)
            return False

    def save_feedback(self, session_id: str, message_id: str, rating: int) -> bool:
        """Store feedback for a generated chat response.

        Args:
            session_id: Chat session identifier.
            message_id: Response message identifier.
            rating: Feedback rating, where 1 means helpful and -1 means not helpful.

        Returns:
            True when the feedback write succeeds.
        """

        if not self.available or not self.db:
            logger.warning("Save feedback requested but Firebase unavailable")
            return False

        if rating not in (-1, 1):
            logger.warning("Invalid feedback rating")
            return False

        try:
            session_ref = self._get_session_reference(session_id)
            feedback_ref = session_ref.collection("feedback").document(message_id)
            feedback_ref.set({
                "rating": rating,
                "helpful": rating > 0,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }, merge=True)
            logger.info("Feedback saved for session %s message %s", session_id, message_id)
            return True

        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.error("Error saving feedback", exc_info=True)
            return False

    def is_available(self) -> bool:
        """Check if Firebase service is available."""
        return self.available

    def get_call_count(self) -> int:
        """Get the number of API calls made."""
        return self.call_count


# Singleton instance
_firebase_service: Optional[FirebaseService] = None


def get_firebase_service() -> FirebaseService:
    """Get or create the Firebase service instance."""
    global _firebase_service
    if _firebase_service is None:
        _firebase_service = FirebaseService()
    return _firebase_service
