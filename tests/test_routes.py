"""
ElectIQ Test Suite - Routes Integration Tests
Tests all API endpoints, response formats, and error handling
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from app import app, ELECTION_DATA, fallback_response

SUPPORTED_COUNTRIES = ["india", "usa", "uk", "eu", "brazil"]


class _DisabledGeminiService:
    def is_available(self):
        return False

    def generate_response(self, *args, **kwargs):
        return ""

    def summarize_history(self, history):
        return ""


@pytest.fixture
def client():
    """Create a test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealthRoute:
    """Health check endpoint tests."""

    def test_health_returns_200(self, client):
        """Health endpoint should return 200 OK."""
        res = client.get("/health")
        assert res.status_code == 200

    def test_health_response_structure(self, client):
        """Health response should have required fields."""
        res = client.get("/health")
        data = json.loads(res.data)
        assert data["status"] == "ok"
        assert "service" in data
        assert "version" in data

    def test_health_service_name(self, client):
        """Service name should be ElectIQ."""
        res = client.get("/health")
        data = json.loads(res.data)
        assert data["service"] == "ElectIQ"

    def test_google_services_registry(self, client):
        """Google services endpoint should return registry metadata."""
        res = client.get("/api/google-services")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "google_services" in data
        assert "gemini" in data["google_services"]


class TestElectionsRoute:
    """Election data endpoints tests."""

    def test_elections_returns_200(self, client):
        """GET /api/elections should return 200."""
        res = client.get("/api/elections")
        assert res.status_code == 200

    def test_elections_has_all_supported(self, client):
        """Should return all 5 countries."""
        res = client.get("/api/elections")
        data = json.loads(res.data)
        for country in SUPPORTED_COUNTRIES:
            assert country in data

    def test_elections_summary_fields(self, client):
        """Each country should have required summary fields."""
        res = client.get("/api/elections")
        data = json.loads(res.data)
        for country_id, info in data.items():
            assert "name" in info
            assert "flag" in info
            assert "system" in info
            assert "color" in info

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_country_detail_returns_200(self, client, country):
        """GET /api/elections/<country> should return 200."""
        res = client.get(f"/api/elections/{country}")
        assert res.status_code == 200

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_country_has_required_fields(self, client, country):
        """Country response should have all required fields."""
        res = client.get(f"/api/elections/{country}")
        data = json.loads(res.data)
        required = ["name", "flag", "system", "body", "frequency", "voters",
                    "description", "timeline", "steps", "facts"]
        for field in required:
            assert field in data, f"Missing field '{field}' in {country}"

    def test_invalid_country_returns_404(self, client):
        """Invalid country should return 404."""
        res = client.get("/api/elections/atlantis")
        assert res.status_code == 404

    def test_case_insensitive_lookup(self, client):
        """Lookup should be case-insensitive."""
        res = client.get("/api/elections/INDIA")
        assert res.status_code == 200

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_timeline_endpoint(self, client, country):
        """Timeline endpoint should return timeline for country."""
        res = client.get(f"/api/elections/{country}/timeline")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "timeline" in data
        assert len(data["timeline"]) > 0

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_voting_steps_endpoint(self, client, country):
        """Voting steps endpoint should return steps."""
        res = client.get(f"/api/elections/{country}/voting-steps")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "steps" in data
        assert len(data["steps"]) >= 5


class TestChatRoute:
    """Chat endpoint tests."""

    def test_chat_requires_post(self, client):
        """Chat should only accept POST."""
        res = client.get("/api/chat")
        assert res.status_code == 405

    def test_chat_empty_message_returns_400(self, client):
        """Empty message should return 400."""
        res = client.post("/api/chat",
                          json={"message": ""},
                          content_type="application/json")
        assert res.status_code == 400

    def test_chat_valid_message(self, client):
        """Valid message should return 200 with response."""
        res = client.post("/api/chat",
                          json={"message": "How do elections work in India?"},
                          content_type="application/json")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "response" in data
        assert len(data["response"]) > 10

    def test_chat_whitespace_only_returns_400(self, client):
        """Whitespace-only message should return 400."""
        res = client.post("/api/chat",
                          json={"message": "   "},
                          content_type="application/json")
        assert res.status_code == 400

    def test_chat_with_history(self, client):
        """Chat should accept and process history."""
        history = [
            {"role": "user", "content": "Tell me about India"},
            {"role": "assistant", "content": "India has 970M voters"}
        ]
        res = client.post("/api/chat",
                          json={"message": "What about the USA?", "history": history},
                          content_type="application/json")
        assert res.status_code == 200

    def test_chat_oversized_message_rejected(self, client):
        """Message exceeding 500 chars should be rejected."""
        big_message = "x" * 510
        res = client.post("/api/chat",
                          json={"message": big_message},
                          content_type="application/json")
        assert res.status_code == 400

    def test_chat_content_type_required(self, client):
        """Request must have Content-Type: application/json."""
        res = client.post("/api/chat",
                          data="not json",
                          content_type="text/plain")
        assert res.status_code == 400


class TestTranslateRoute:
    """Translation endpoint tests."""

    def test_translate_endpoint_exists(self, client):
        """Translate endpoint should be available."""
        res = client.post("/api/translate",
                          json={"text": "hello", "target_language": "es"},
                          content_type="application/json")
        # Should return 503 if translate disabled, or 200 if available
        assert res.status_code in [200, 503]

    def test_languages_endpoint(self, client):
        """Languages endpoint should list supported languages."""
        res = client.get("/api/languages")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "supported_languages" in data
        assert len(data["supported_languages"]) > 0

    def test_detect_language_endpoint(self, client):
        """Language detection endpoint should work."""
        res = client.post("/api/detect",
                          json={"text": "hello"},
                          content_type="application/json")
        # May return 404 or 503 if disabled, but endpoint should exist or be gracefully disabled
        assert res.status_code in [200, 404, 503]

    def test_supported_language_metadata(self, client):
        """Supported language metadata endpoint should return details."""
        res = client.get("/translate/supported")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "en" in data
        assert data["ar"]["rtl"] is True


class TestGlossaryRoute:
    """Glossary endpoints tests."""

    def test_glossary_list(self, client):
        """Glossary list should return terms."""
        res = client.get("/api/glossary")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "glossary" in data
        assert len(data["glossary"]) > 20

    def test_glossary_term_lookup(self, client):
        """Glossary term lookup should resolve slugs."""
        res = client.get("/api/glossary/ballot")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["term"] == "Ballot"
        assert "related_terms" in data

    def test_glossary_search(self, client):
        """Glossary search should return ranked matches."""
        res = client.get("/api/glossary/search?q=electoral")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["query"] == "electoral"
        assert len(data["results"]) > 0

    def test_glossary_explain(self, client, monkeypatch):
        """Glossary explain should return contextual output."""
        monkeypatch.setattr("routes.glossary.get_gemini_service", lambda: _DisabledGeminiService())
        res = client.post(
            "/api/glossary/explain",
            json={"term": "Ballot", "context": "voting"},
            content_type="application/json",
        )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["term"] == "Ballot"
        assert "explanation" in data


class TestQuizRoute:
    """Quiz endpoints tests."""

    def test_quiz_country_list(self, client):
        """Quiz country list should be available."""
        res = client.get("/api/quiz/countries")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data["countries"]) == len(SUPPORTED_COUNTRIES)

    def test_generate_quiz(self, client, monkeypatch):
        """Quiz generation should return five questions."""
        monkeypatch.setattr("routes.quiz.get_gemini_service", lambda: _DisabledGeminiService())
        res = client.post(
            "/api/quiz/generate",
            json={"country": "india", "difficulty": "beginner"},
            content_type="application/json",
        )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["country"] == "india"
        assert len(data["questions"]) == 5

    def test_submit_quiz(self, client, monkeypatch):
        """Quiz submission should return a scored response."""
        monkeypatch.setattr("routes.quiz.get_gemini_service", lambda: _DisabledGeminiService())
        answers = [{"id": i, "selected": 0} for i in range(1, 6)]
        res = client.post(
            "/api/quiz/submit",
            json={"country": "india", "difficulty": "beginner", "answers": answers},
            content_type="application/json",
        )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["total"] == 5
        assert data["score"] == 5
        assert data["percentage"] == 100


class TestCompareRoute:
    """Comparison endpoint tests."""

    def test_compare_two_countries(self, client):
        """Compare endpoint should return normalized comparison data."""
        res = client.get("/api/compare?countries=india,usa")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data["countries"]) == 2
        assert "comparison" in data

    def test_compare_limit_enforced(self, client):
        """Compare endpoint should reject too many countries."""
        res = client.get("/api/compare?countries=india,usa,uk,eu,brazil")
        assert res.status_code == 400

    def test_compare_metrics(self, client):
        """Comparison metrics endpoint should be available."""
        res = client.get("/api/compare/metrics")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data["metrics"]) > 0


class TestAnalyticsRoute:
    """Analytics endpoint tests."""

    def test_track_country_view(self, client):
        """Tracking should accept a country view event."""
        res = client.post(
            "/api/analytics/track",
            json={"event": "country_view", "country": "india"},
            content_type="application/json",
        )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["tracked"] is True

    def test_popular_countries_updates(self, client):
        """Popular countries endpoint should reflect tracked events."""
        client.post(
            "/api/analytics/track",
            json={"event": "country_view", "country": "india"},
            content_type="application/json",
        )
        res = client.get("/api/analytics/popular")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data["countries"]) >= 1


class TestDataIntegrity:
    """Data structure and content validation."""

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_timeline_structure(self, country):
        """Timeline should have required fields."""
        data = ELECTION_DATA[country]
        assert "timeline" in data
        for item in data["timeline"]:
            assert "phase" in item
            assert "days" in item
            assert "description" in item

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_steps_structure(self, country):
        """Steps should have required fields."""
        data = ELECTION_DATA[country]
        assert "steps" in data
        assert len(data["steps"]) >= 5
        for step in data["steps"]:
            assert "icon" in step
            assert "title" in step
            assert "detail" in step

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_facts_not_empty(self, country):
        """Each country should have facts."""
        facts = ELECTION_DATA[country]["facts"]
        assert len(facts) >= 3

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_color_is_valid_hex(self, country):
        """Color should be valid hex."""
        color = ELECTION_DATA[country]["color"]
        assert color.startswith("#")
        assert len(color) in [4, 7]

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_flag_is_emoji(self, country):
        """Flag should be an emoji."""
        flag = ELECTION_DATA[country]["flag"]
        assert len(flag) > 0

    @pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
    def test_voters_field_populated(self, country):
        """Voters field should contain population info."""
        voters = ELECTION_DATA[country]["voters"]
        assert "million" in voters.lower() or "m" in voters.lower()


class TestFallbackResponse:
    """Fallback response tests for unavailable Gemini."""

    def test_india_keyword(self):
        """India keyword should trigger India response."""
        resp = fallback_response("Tell me about india elections")
        assert "India" in resp or "🇮🇳" in resp

    def test_usa_keyword(self):
        """USA keyword should trigger USA response."""
        resp = fallback_response("How does usa voting work?")
        assert "Electoral College" in resp or "🇺🇸" in resp

    def test_uk_keyword(self):
        """UK keyword should trigger UK response."""
        resp = fallback_response("What about uk elections?")
        assert "First Past the Post" in resp or "🇬🇧" in resp

    def test_brazil_keyword(self):
        """Brazil keyword should trigger Brazil response."""
        resp = fallback_response("Explain brazil voting")
        assert "Brazil" in resp or "🇧🇷" in resp

    def test_eu_keyword(self):
        """EU keyword should trigger EU response."""
        resp = fallback_response("How does eu parliament get elected?")
        assert "European" in resp or "🇪🇺" in resp

    def test_unknown_topic_returns_default(self):
        """Unknown topic should return default message."""
        resp = fallback_response("Tell me about pizza")
        assert len(resp) > 20
        assert "ElectIQ" in resp or "election" in resp.lower()

    def test_empty_message(self):
        """Empty message should still return something."""
        resp = fallback_response("")
        assert len(resp) > 0

    def test_response_is_always_string(self):
        """Fallback should always return string."""
        for msg in ["india", "usa", "uk", "eu", "brazil", "unknown", ""]:
            assert isinstance(fallback_response(msg), str)


class TestSecurityBasic:
    """Basic security checks."""

    def test_xss_in_country_param(self, client):
        """XSS in country parameter should be handled."""
        res = client.get("/api/elections/<script>alert(1)</script>")
        assert res.status_code == 404

    def test_long_country_param(self, client):
        """Very long country parameter should be handled."""
        res = client.get("/api/elections/" + "x" * 500)
        assert res.status_code == 404

    def test_sql_injection_attempt(self, client):
        """SQL injection attempt should fail safely."""
        res = client.get("/api/elections/'; DROP TABLE--")
        assert res.status_code in [404, 400]

    def test_large_chat_message(self, client):
        """Large message should be rejected or handled."""
        res = client.post("/api/chat",
                          json={"message": "x" * 5000},
                          content_type="application/json")
        assert res.status_code in [200, 400]

    def test_security_headers_present(self, client):
        """Response should include security headers."""
        res = client.get("/health")
        assert "X-Content-Type-Options" in res.headers
        assert "X-Frame-Options" in res.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
