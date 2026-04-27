"""Google Cloud Storage service for caching and export features.

The service wraps a small storage surface used for cached AI responses and
exporting election snapshots.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from google.cloud import storage
from google.cloud.storage import Blob, Client as StorageClient

logger = logging.getLogger(__name__)


class CloudStorageService:
    """Google Cloud Storage for election data and export features."""

    def __init__(self) -> None:
        self.client: Optional[StorageClient] = None
        self.bucket_name: str = os.getenv("GCS_BUCKET", "electiq-data")
        self._initialize()

    def _initialize(self) -> None:
        """Initialize the Storage client if credentials are available."""

        try:
            self.client = storage.Client()
            logger.info("Cloud Storage client initialized")
        except Exception as exc:  # pragma: no cover - integration fallback
            logger.warning("Cloud Storage unavailable: %s", exc)
            self.client = None

    def _get_bucket(self) -> Optional[Any]:
        """Return the configured bucket when the client is available."""

        if not self.client:
            return None
        return self.client.bucket(self.bucket_name)

    def export_election_data(self, country_id: str, data: Dict[str, Any]) -> Optional[str]:
        """Export election data snapshot to Cloud Storage."""

        bucket = self._get_bucket()
        if not bucket:
            return None

        try:
            blob_name = f"exports/{country_id}.json"
            blob = bucket.blob(blob_name)
            blob.upload_from_string(json.dumps(data, ensure_ascii=False), content_type="application/json")
            return f"gs://{self.bucket_name}/{blob_name}"
        except Exception as exc:  # pragma: no cover - integration fallback
            logger.error("Cloud Storage export failed", exc_info=True)
            return None

    def get_cached_ai_response(self, cache_key: str) -> Optional[str]:
        """Retrieve cached AI response from Cloud Storage."""

        bucket = self._get_bucket()
        if not bucket:
            return None

        try:
            blob: Blob = bucket.blob(f"cache/{cache_key}.txt")
            if not blob.exists():
                return None
            return blob.download_as_text()
        except Exception as exc:  # pragma: no cover - integration fallback
            logger.error("Cloud Storage cache read failed", exc_info=True)
            return None

    def cache_ai_response(self, cache_key: str, response: str) -> bool:
        """Cache AI response in Cloud Storage for efficiency."""

        bucket = self._get_bucket()
        if not bucket:
            return False

        try:
            blob: Blob = bucket.blob(f"cache/{cache_key}.txt")
            blob.upload_from_string(response, content_type="text/plain")
            return True
        except Exception as exc:  # pragma: no cover - integration fallback
            logger.error("Cloud Storage cache write failed", exc_info=True)
            return False


_cloud_storage_service: Optional[CloudStorageService] = None


def get_cloud_storage_service() -> CloudStorageService:
    """Return the shared Cloud Storage service instance."""

    global _cloud_storage_service
    if _cloud_storage_service is None:
        _cloud_storage_service = CloudStorageService()
    return _cloud_storage_service