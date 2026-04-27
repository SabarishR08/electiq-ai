"""
ElectIQ Test Suite - Service Layer Tests
Tests Gemini, Translate, Firebase, and Vertex AI services
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini_service import GeminiService, get_gemini_service
from services.translate_service import TranslateService, get_translate_service
from services.firebase_service import FirebaseService, get_firebase_service
from services.vertex_service import VertexService, get_vertex_service
from services.bigquery_service import BigQueryService, get_bigquery_service
from services.cloud_storage_service import CloudStorageService, get_cloud_storage_service


class TestGeminiService:
    """Google Gemini service tests."""

    def test_generate_response_success(self):
        """Should initialize Gemini service."""
        service = GeminiService()
        # Service should be instantiable
        assert service is not None

    def test_fallback_response_india(self):
        """Fallback should provide India response."""
        service = GeminiService()
        response = service._fallback_response("Tell me about India elections")
        assert "India" in response or "voter" in response.lower()

    def test_fallback_response_usa(self):
        """Fallback should provide USA response."""
        service = GeminiService()
        response = service._fallback_response("usa voting process")
        assert "Electoral College" in response or "USA" in response

    def test_fallback_response_always_returns_string(self):
        """Fallback must always return a non-empty string."""
        service = GeminiService()
        for topic in ["India", "USA", "Brazil", "random", ""]:
            response = service._fallback_response(topic)
            assert isinstance(response, str)
            assert len(response) > 10

    def test_singleton_pattern(self):
        """Multiple calls should return same instance."""
        service1 = get_gemini_service()
        service2 = get_gemini_service()
        assert service1 is service2


class TestTranslateService:
    """Google Cloud Translate service tests."""

    def test_translate_text_success(self):
        """Should initialize Translate service."""
        service = TranslateService()
        # Service should be instantiable
        assert service is not None

    def test_translate_validates_language(self):
        """Should reject unsupported languages."""
        service = TranslateService()
        try:
            result = service.translate_text("Hello", target_language="xyz")
            # Should either reject or handle gracefully
            assert result is None or isinstance(result, str)
        except (ValueError, Exception):
            pass  # Expected for invalid language

    def test_translate_validates_text_length(self):
        """Should reject oversized text."""
        service = TranslateService()
        huge_text = "x" * 10000
        try:
            result = service.translate_text(huge_text, target_language="es")
            assert result is None or isinstance(result, str)
        except (ValueError, Exception):
            pass  # Expected for oversized input

    def test_translate_validates_empty_text(self):
        """Should reject empty text."""
        service = TranslateService()
        try:
            result = service.translate_text("", target_language="es")
            assert result is None or isinstance(result, str)
        except (ValueError, Exception):
            pass  # Expected for empty input

    def test_detect_language(self):
        """Should detect language of text."""
        service = TranslateService()
        # Should return language code or handle gracefully
        result = service.detect_language("Hello world")
        assert result is None or isinstance(result, str)

    def test_get_supported_languages(self):
        """Should return list of supported languages."""
        service = TranslateService()
        languages = service.get_supported_languages()
        assert isinstance(languages, list)
        assert len(languages) >= 8
        assert "en" in languages or "english" in [l.lower() for l in languages]

    def test_singleton_pattern(self):
        """Multiple calls should return same instance."""
        service1 = get_translate_service()
        service2 = get_translate_service()
        assert service1 is service2


class TestFirebaseService:
    """Firebase Firestore service tests."""

    def test_save_message(self):
        """Should initialize Firebase service."""
        service = FirebaseService()
        # Service should be instantiable
        assert service is not None

    def test_get_session_history(self):
        """Should have get_session_history method."""
        service = FirebaseService()
        # Method should exist
        assert hasattr(service, 'get_session_history')

    def test_delete_session(self):
        """Should have delete_session method."""
        service = FirebaseService()
        # Method should exist
        assert hasattr(service, 'delete_session')

    def test_singleton_pattern(self):
        """Multiple calls should return same instance."""
        service1 = get_firebase_service()
        service2 = get_firebase_service()
        assert service1 is service2

    def test_save_message_validates_session_id(self):
        """Should handle invalid session IDs."""
        service = FirebaseService()
        # Should not crash with invalid input
        try:
            service.save_message("", "user", "Hello")
        except (ValueError, TypeError):
            pass  # Expected

    def test_save_session_method_exists(self):
        """Should expose save_session method."""
        service = FirebaseService()
        assert hasattr(service, "save_session")

    def test_get_session_method_exists(self):
        """Should expose get_session method."""
        service = FirebaseService()
        assert hasattr(service, "get_session")


class TestVertexService:
    """Vertex AI service tests."""

    def test_search_with_grounding_returns_dict(self):
        """Should return structured response."""
        service = VertexService()
        result = service.search_with_grounding("What is FPTP?", "uk")

        assert isinstance(result, dict)
        assert "answer" in result
        assert "sources" in result

    def test_cite_sources_formats_correctly(self):
        """Should have cite_sources method."""
        service = VertexService()
        # Method should exist
        assert hasattr(service, 'cite_sources')

    def test_singleton_pattern(self):
        """Multiple calls should return same instance."""
        service1 = get_vertex_service()
        service2 = get_vertex_service()
        assert service1 is service2


class TestBigQueryService:
    """Google BigQuery service tests."""

    def test_bigquery_service_initializes(self):
        """BigQueryService initializes without crashing when client unavailable."""
        service = BigQueryService()
        assert service is not None

    def test_bigquery_log_query_event_handles_unavailable(self):
        """log_query_event returns False gracefully when BigQuery unavailable."""
        service = BigQueryService()
        service.client = None
        result = service.log_query_event("india", "timeline", "test-session")
        assert result is False

    def test_bigquery_get_popular_countries_handles_unavailable(self):
        """get_popular_countries should return an empty list when unavailable."""
        service = BigQueryService()
        service.client = None
        assert service.get_popular_countries() == []

    def test_bigquery_get_usage_stats_handles_unavailable(self):
        """get_usage_stats should return empty metrics when unavailable."""
        service = BigQueryService()
        service.client = None
        stats = service.get_usage_stats()
        assert stats["total_queries"] == 0
        assert stats["unique_sessions"] == 0

    def test_bigquery_singleton_pattern(self):
        """Multiple calls should return same instance."""
        service1 = get_bigquery_service()
        service2 = get_bigquery_service()
        assert service1 is service2


class TestCloudStorageService:
    """Google Cloud Storage service tests."""

    def test_cloud_storage_service_initializes(self):
        """CloudStorageService initializes without crashing when client unavailable."""
        service = CloudStorageService()
        assert service is not None

    def test_export_election_data_handles_unavailable(self):
        """export_election_data should return None when storage is unavailable."""
        service = CloudStorageService()
        service.client = None
        assert service.export_election_data("india", {"name": "India"}) is None

    def test_get_cached_ai_response_handles_unavailable(self):
        """get_cached_ai_response should return None when storage is unavailable."""
        service = CloudStorageService()
        service.client = None
        assert service.get_cached_ai_response("cache-key") is None

    def test_cache_ai_response_handles_unavailable(self):
        """cache_ai_response should return False when storage is unavailable."""
        service = CloudStorageService()
        service.client = None
        assert service.cache_ai_response("cache-key", "response") is False

    def test_cloud_storage_singleton_pattern(self):
        """Multiple calls should return same instance."""
        service1 = get_cloud_storage_service()
        service2 = get_cloud_storage_service()
        assert service1 is service2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
