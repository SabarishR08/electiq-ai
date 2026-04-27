"""Google BigQuery service for election analytics and usage tracking.

The service encapsulates BigQuery initialization and the small analytics query
surface used by the application and tests.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from google.cloud import bigquery
from google.cloud.bigquery import Client, QueryJobConfig, SchemaField
from google.cloud.exceptions import GoogleCloudError

logger = logging.getLogger(__name__)


class BigQueryService:
    """Google BigQuery service for election analytics and usage tracking."""

    def __init__(self) -> None:
        self.client: Optional[Client] = None
        self.project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.dataset_id: str = "electiq_analytics"
        self._initialize()

    def _initialize(self) -> None:
        """Initialize the BigQuery client when the dependency is available."""

        try:
            self.client = bigquery.Client(project=self.project_id or None)
            logger.info("BigQuery client initialized")
        except Exception as exc:  # pragma: no cover - integration fallback
            logger.warning("BigQuery unavailable: %s", exc)
            self.client = None

    def _build_table_id(self) -> str:
        """Return the fully qualified query-events table identifier."""

        if self.project_id:
            return f"{self.project_id}.{self.dataset_id}.query_events"
        return f"{self.dataset_id}.query_events"

    def _get_query_config(self) -> QueryJobConfig:
        """Return a reusable BigQuery job configuration."""

        return QueryJobConfig()

    def log_query_event(self, country: str, query_type: str, session_id: str) -> bool:
        """Log a user query event to BigQuery for analytics."""

        if not self.client:
            return False

        try:
            table_id = self._build_table_id()
            rows = [{
                "country": country,
                "query_type": query_type,
                "session_id": session_id,
            }]
            errors = self.client.insert_rows_json(table_id, rows)
            if errors:
                logger.warning("BigQuery insert errors: %s", errors)
                return False
            return True
        except GoogleCloudError as exc:
            logger.error("BigQuery event logging failed", exc_info=True)
            return False

    def get_popular_countries(self) -> List[Dict[str, Any]]:
        """Query most explored countries from BigQuery."""

        if not self.client:
            return []

        try:
            query = f"""
                SELECT country, COUNT(*) AS queries
                FROM `{self._build_table_id()}`
                GROUP BY country
                ORDER BY queries DESC
                LIMIT 10
            """
            job_config = self._get_query_config()
            job = self.client.query(query, job_config=job_config)
            return [{"country": row[0], "queries": int(row[1])} for row in job]
        except GoogleCloudError as exc:
            logger.error("BigQuery popular countries query failed", exc_info=True)
            return []

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get aggregated usage statistics from BigQuery."""

        if not self.client:
            return {"total_queries": 0, "unique_sessions": 0, "top_topics": []}

        try:
            query = f"""
                SELECT
                    COUNT(*) AS total_queries,
                    COUNT(DISTINCT session_id) AS unique_sessions
                FROM `{self._build_table_id()}`
            """
            rows = list(self.client.query(query, job_config=self._get_query_config()))
            total_queries = int(rows[0][0]) if rows else 0
            unique_sessions = int(rows[0][1]) if rows else 0
            return {
                "total_queries": total_queries,
                "unique_sessions": unique_sessions,
                "top_topics": self.get_popular_countries(),
            }
        except GoogleCloudError as exc:
            logger.error("BigQuery usage stats query failed", exc_info=True)
            return {"total_queries": 0, "unique_sessions": 0, "top_topics": []}


_bigquery_service: Optional[BigQueryService] = None


def get_bigquery_service() -> BigQueryService:
    """Return the shared BigQuery service instance."""

    global _bigquery_service
    if _bigquery_service is None:
        _bigquery_service = BigQueryService()
    return _bigquery_service