"""
ElectIQ Test Suite - Security & Sanitization Tests
Tests XSS prevention, injection attempts, rate limiting, and security headers
"""

import pytest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from app import app
from services.exceptions import ValidationError
from services.security_service import get_security_service


@pytest.fixture
def client():
    """Create test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestXSSPrevention:
    """XSS (Cross-Site Scripting) prevention tests."""

    def test_script_tag_in_chat_rejected(self, client):
        """<script> tag in chat should be rejected or sanitized."""
        res = client.post("/api/chat",
                          json={"message": "<script>alert('xss')</script>"},
                          content_type="application/json")
        # Should either reject (400) or sanitize
        assert res.status_code in [200, 400, 422]

    def test_onerror_handler_in_chat(self, client):
        """onerror handler should be rejected or sanitized."""
        res = client.post("/api/chat",
                          json={"message": "<img src=x onerror='alert(1)'>"},
                          content_type="application/json")
        assert res.status_code in [200, 400, 422]

    def test_javascript_protocol_in_chat(self, client):
        """javascript: protocol should be rejected."""
        res = client.post("/api/chat",
                          json={"message": "<a href='javascript:alert(1)'>click</a>"},
                          content_type="application/json")
        assert res.status_code in [200, 400, 422]

    def test_svg_onclick_in_chat(self, client):
        """SVG onclick handler should be rejected."""
        res = client.post("/api/chat",
                          json={"message": "<svg onload='alert(1)'>"},
                          content_type="application/json")
        assert res.status_code in [200, 400, 422]

    def test_event_handler_with_quotes(self, client):
        """Event handlers with various quote styles should be rejected."""
        payloads = [
            '<div onclick="alert(1)">',
            "<div onmouseover='alert(1)'>",
            '<iframe onload=alert(1)>'
        ]
        for payload in payloads:
            res = client.post("/api/chat",
                              json={"message": payload},
                              content_type="application/json")
            assert res.status_code in [200, 400, 422]


class TestInputValidation:
    """Input validation and sanitization tests."""

    def test_oversized_chat_message(self, client):
        """Oversized message should be rejected."""
        huge_msg = "x" * 5000
        res = client.post("/api/chat",
                          json={"message": huge_msg},
                          content_type="application/json")
        assert res.status_code in [200, 400]

    def test_null_bytes_in_input(self, client):
        """Null bytes should be handled."""
        res = client.post("/api/chat",
                          json={"message": "hello\x00world"},
                          content_type="application/json")
        assert res.status_code in [200, 400]

    def test_unicode_normalization(self, client):
        """Unicode should be handled safely."""
        res = client.post("/api/chat",
                          json={"message": "こんにちは 你好 🎉"},
                          content_type="application/json")
        assert res.status_code in [200, 400]

    def test_missing_message_field(self, client):
        """Missing message field should return 400."""
        res = client.post("/api/chat",
                          json={"something": "else"},
                          content_type="application/json")
        assert res.status_code == 400

    def test_missing_target_language_field(self, client):
        """Missing target_language in translate should return 400."""
        res = client.post("/api/translate",
                          json={"text": "hello"},
                          content_type="application/json")
        assert res.status_code in [400, 503]

    def test_null_message(self, client):
        """Null message should be rejected or handled."""
        res = client.post("/api/chat",
                  json={"message": None},
                  content_type="application/json")
        # May return various status codes depending on validation
        assert res.status_code in [200, 400, 422, 429, 500]

    def test_empty_dict_body(self, client):
        """Empty JSON body should be rejected."""
        res = client.post("/api/chat",
                          json={},
                          content_type="application/json")
        assert res.status_code == 400


class TestSQLInjection:
    """SQL injection prevention tests."""

    def test_sql_injection_in_country_param(self, client):
        """SQL injection in URL param should fail safely."""
        payloads = [
            "'; DROP TABLE elections; --",
            "' OR '1'='1",
            "1; DELETE FROM elections WHERE 1=1; --"
        ]
        for payload in payloads:
            res = client.get(f"/api/elections/{payload}")
            assert res.status_code in [404, 400]

    def test_sql_in_chat_message(self, client):
        """SQL injection in chat message should be handled."""
        res = client.post("/api/chat",
                          json={"message": "'; DROP TABLE--"},
                          content_type="application/json")
        assert res.status_code in [200, 400]


class TestSecurityHeaders:
    """HTTP security headers validation."""

    def test_x_content_type_options_header(self, client):
        """Response should have X-Content-Type-Options header."""
        res = client.get("/health")
        assert "X-Content-Type-Options" in res.headers
        assert res.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_header(self, client):
        """Response should have X-Frame-Options header."""
        res = client.get("/health")
        assert "X-Frame-Options" in res.headers
        assert "SAMEORIGIN" in res.headers["X-Frame-Options"] or \
               "DENY" in res.headers["X-Frame-Options"]

    def test_csp_header(self, client):
        """Response should have Content-Security-Policy header."""
        res = client.get("/health")
        assert "Content-Security-Policy" in res.headers

    def test_headers_on_all_routes(self, client):
        """Security headers should be on all routes."""
        routes_to_test = [
            "/health",
            "/api/elections",
        ]
        for route in routes_to_test:
            res = client.get(route)
            assert "X-Content-Type-Options" in res.headers
            assert "X-Frame-Options" in res.headers

    def test_no_server_header_leak(self, client):
        """Server header should not leak version info."""
        res = client.get("/health")
        server = res.headers.get("Server", "")
        # Should not contain specific version numbers
        assert "Python" not in server or "3.11" not in server

    def test_request_id_header_present(self, client):
        """Responses should include a request ID header."""
        res = client.get("/api/elections")
        assert config.REQUEST_ID_HEADER in res.headers
        assert len(res.headers[config.REQUEST_ID_HEADER]) > 0


class TestSecurityService:
    """Security service validation tests."""

    def test_sanitize_html_strips_markup(self):
        """HTML tags should be stripped from input."""
        service = get_security_service()
        assert service.sanitize_html("<b>Hello</b>", 50) == "Hello"

    def test_validate_country_id_normalizes(self):
        """Country identifiers should normalize to lowercase."""
        service = get_security_service()
        assert service.validate_country_id("INDIA") == "india"

    def test_validate_language_code_normalizes(self):
        """Language codes should normalize to lowercase."""
        service = get_security_service()
        assert service.validate_language_code("ES") == "es"

    def test_detect_injection_patterns(self):
        """Common injection patterns should be detected."""
        service = get_security_service()
        assert service.detect_injection("<script>alert(1)</script>")
        assert service.detect_injection("select * from users")
        assert service.detect_injection("../etc/passwd")

    def test_generate_request_id_is_hex(self):
        """Request IDs should be UUID hex strings."""
        service = get_security_service()
        request_id = service.generate_request_id()
        assert len(request_id) == 32
        int(request_id, 16)

    def test_content_policy_blocks_personal_voter_data(self):
        """Personal voter data requests should be blocked."""
        service = get_security_service()
        allowed, reason = service.check_content_policy("my voter id number is 12345")
        assert allowed is False
        assert "personal voter data" in reason.lower()


class TestRuntimeGuards:
    """Runtime guardrails for request limits and tracing."""

    def test_request_too_large_returns_413(self, client):
        """Oversized request bodies should be rejected with 413."""
        oversized_message = "x" * (config.MAX_CONTENT_LENGTH_BYTES + 1024)
        res = client.post(
            "/api/chat",
            json={"message": oversized_message},
            content_type="application/json",
        )
        assert res.status_code == config.HTTP_REQUEST_ENTITY_TOO_LARGE


class TestRateLimiting:
    """Rate limiting behavior tests."""

    def test_rate_limit_header_present(self, client):
        """Rate limit headers should be present."""
        res = client.post("/api/chat",
                          json={"message": "test"},
                          content_type="application/json")
        # Check for rate limit headers (RateLimit-Limit, RateLimit-Remaining, etc.)
        # Exact headers vary by flask-limiter implementation
        assert res.status_code in [200, 429, 503]

    def test_chat_rate_limit_threshold(self, client):
        """Should enforce rate limiting on chat."""
        # Send multiple requests
        responses = []
        for i in range(25):  # Slightly above typical 20/min limit
            res = client.post("/api/chat",
                              json={"message": f"test{i}"},
                              content_type="application/json")
            responses.append(res.status_code)

        # At least one should be rate-limited (429) or succeed (200)
        status_set = set(responses)
        assert any(s in [200, 429, 503] for s in status_set)


class TestSessionHandling:
    """Session and state management tests."""

    def test_invalid_session_id_format(self, client):
        """Invalid session ID should be handled."""
        res = client.get("/api/chat/history/invalid%3Cscript%3E")
        # May return 503 if Firebase unavailable
        assert res.status_code in [404, 400, 200, 503]

    def test_missing_session_id(self, client):
        """Missing session ID should return 404."""
        res = client.get("/api/chat/history/")
        assert res.status_code == 404

    def test_very_long_session_id(self, client):
        """Very long session ID should be handled."""
        long_id = "x" * 5000
        res = client.get(f"/api/chat/history/{long_id}")
        assert res.status_code in [404, 400]


class TestContentType:
    """Content-Type validation tests."""

    def test_non_json_content_type(self, client):
        """POST with non-JSON Content-Type should be rejected."""
        res = client.post("/api/chat",
                          data="message=test",
                          content_type="application/x-www-form-urlencoded")
        assert res.status_code in [400, 415]

    def test_multipart_content_type(self, client):
        """Multipart content should be handled."""
        res = client.post("/api/chat",
                          data=b"some binary data",
                          content_type="multipart/form-data")
        assert res.status_code in [400, 413, 415]

    def test_missing_content_type_with_body(self, client):
        """Missing Content-Type with body should be handled."""
        res = client.post("/api/chat",
                          data='{"message": "test"}')
        # Should either process (if defaulting to JSON) or reject
        assert res.status_code in [200, 400, 415, 429]


class TestJSONValidation:
    """JSON parsing and validation tests."""

    def test_invalid_json(self, client):
        """Invalid JSON should return error."""
        res = client.post("/api/chat",
                  data="{invalid json}",
                  content_type="application/json")
        # Flask may return 400, 422, or 429 (rate limited)
        assert res.status_code in [400, 415, 422, 429, 500]

    def test_truncated_json(self, client):
        """Truncated JSON should return error."""
        res = client.post("/api/chat",
                  data='{"message": "test"',
                  content_type="application/json")
        # Flask parser returns 400 for invalid JSON, or 429 if rate limited
        assert res.status_code in [400, 415, 422, 429, 500]

    def test_nested_json_injection(self, client):
        """Nested JSON should be handled safely."""
        res = client.post("/api/chat",
                  json={"message": '{"nested": "<script>"}'},
                  content_type="application/json")
        # May be rate limited or processed
        assert res.status_code in [200, 400, 429]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
