"""ElectIQ Flask application factory and compatibility exports.

The module configures logging, creates the Flask app, registers blueprints, and
keeps the legacy ELECTION_DATA and fallback_response exports used by tests.
"""

import json
import logging
import time
from typing import Any, Mapping

from flask import Flask, Response, g, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google.cloud import logging as cloud_logging

import config
from routes.analytics import analytics_bp
from routes.chat import chat_bp
from routes.compare import compare_bp
from routes.elections import _load_elections_data, elections_bp
from routes.glossary import glossary_bp
from routes.health import health_bp
from routes.quiz import quiz_bp
from routes.translate import translate_bp
from services.security_service import get_security_service

logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)
security_service = get_security_service()


def setup_cloud_logging() -> None:
    """Initialize Google Cloud Logging when the runtime supports it."""

    try:
        client = cloud_logging.Client()
        client.setup_logging()
        logger.info("Google Cloud Logging initialized")
    except Exception as exc:  # pragma: no cover - defensive integration guard
        logger.warning("Cloud Logging unavailable, using local: %s", exc)


def _build_country_summary(elections_data: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build the compact country summary used by the homepage.

    Args:
        elections_data: Full election dataset loaded from JSON.

    Returns:
        A mapping of country IDs to the fields needed by the index template.
    """

    return {
        country_id: {
            "name": country_data.get("name"),
            "flag": country_data.get("flag"),
            "system": country_data.get("system"),
            "color": country_data.get("color"),
        }
        for country_id, country_data in elections_data.items()
    }


def _apply_security_headers(response: Response) -> Response:
    """Apply standard security headers to every HTTP response.

    Args:
        response: Flask response object to update.

    Returns:
        The same response with security headers set.
    """

    response.headers[config.HEADER_CONTENT_TYPE_OPTIONS] = config.HEADER_VALUE_NOSNIFF
    response.headers[config.HEADER_FRAME_OPTIONS] = config.HEADER_VALUE_SAMEORIGIN
    response.headers[config.HEADER_XSS_PROTECTION] = config.HEADER_VALUE_XSS_BLOCK
    response.headers[config.HEADER_REFERRER_POLICY] = config.HEADER_VALUE_STRICT_REFERRER_POLICY
    response.headers[config.HEADER_CONTENT_SECURITY_POLICY] = config.CSP_HEADER
    response.headers[config.HEADER_PERMISSIONS_POLICY] = config.HEADER_VALUE_PERMISSIONS_POLICY
    response.headers[config.HEADER_CROSS_ORIGIN_OPENER_POLICY] = config.HEADER_VALUE_CROSS_ORIGIN_OPENER_POLICY
    response.headers[config.HEADER_CROSS_ORIGIN_RESOURCE_POLICY] = config.HEADER_VALUE_CROSS_ORIGIN_RESOURCE_POLICY
    response.headers[config.HEADER_STRICT_TRANSPORT_SECURITY] = config.HEADER_VALUE_STRICT_TRANSPORT_SECURITY

    if request.path.startswith("/api/"):
        response.headers[config.HEADER_CACHE_CONTROL] = config.HEADER_VALUE_NO_STORE

    return response


def _log_audit_event(response: Response) -> Response:
    """Log a structured audit record for the current request."""

    start_time = getattr(g, "request_start", None)
    duration_ms = int((time.perf_counter() - start_time) * 1000) if start_time is not None else 0
    audit_record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
        "request_id": getattr(g, "request_id", ""),
    }
    logger.info(json.dumps(audit_record, separators=(",", ":")))
    return response


def _attach_request_id(response: Response) -> Response:
    """Attach the generated request ID to the response headers."""

    request_id = getattr(g, "request_id", "")
    if request_id:
        response.headers[config.REQUEST_ID_HEADER] = request_id
    return response


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns:
        Configured Flask app instance.
    """

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["TESTING"] = config.TESTING
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH_BYTES
    setup_cloud_logging()

    if config.RATELIMIT_ENABLED:
        Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"],
            storage_uri=config.RATELIMIT_STORAGE_URI,
        )
        logger.info("Rate limiting enabled")

    @app.before_request
    def _prepare_request_context() -> None:
        """Initialize tracing context before each request."""

        g.request_start = time.perf_counter()
        g.request_id = security_service.generate_request_id()

    app.after_request(_apply_security_headers)
    app.after_request(_attach_request_id)
    app.after_request(_log_audit_event)

    @app.errorhandler(413)
    def request_too_large(_: Exception) -> tuple[dict[str, Any], int]:
        """Return a JSON payload for oversized requests."""

        return jsonify({"error": config.ERROR_REQUEST_TOO_LARGE, "max_size_bytes": config.MAX_CONTENT_LENGTH_BYTES}), config.HTTP_REQUEST_ENTITY_TOO_LARGE

    @app.route("/")
    def index() -> str:
        """Render the main application template.

        Returns:
            Rendered HTML for the landing page.
        """

        elections_data = _load_elections_data()
        countries = _build_country_summary(elections_data)
        return render_template("index.html", countries=countries)

    app.register_blueprint(health_bp)
    app.register_blueprint(elections_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(translate_bp)
    app.register_blueprint(quiz_bp, url_prefix="/api")
    app.register_blueprint(glossary_bp, url_prefix="/api")
    app.register_blueprint(compare_bp, url_prefix="/api")
    app.register_blueprint(analytics_bp, url_prefix="/api")

    logger.info("Flask application created and configured")
    return app


app = create_app()
ELECTION_DATA = _load_elections_data()


def _build_fallback_response(message: str) -> str:
    """Select a fallback answer for common election topics.

    Args:
        message: User prompt to match against topic keywords.

    Returns:
        A deterministic fallback response string.
    """

    msg_lower = message.lower()
    responses = [
        (("india",), "🇮🇳 India uses a Parliamentary system. The Election Commission of India (ECI) oversees elections. Citizens vote for 543 Lok Sabha seats every 5 years using Electronic Voting Machines (EVMs). The party or coalition with 272+ seats forms the government."),
        (("usa", "america", "united states"), "🇺🇸 The USA holds Presidential elections every 4 years. Citizens don't directly elect the President — they vote for Electors who form the Electoral College (538 total). A candidate needs 270 electoral votes to win."),
        (("uk", "britain", "england"), "🇬🇧 The UK uses First Past the Post voting. Citizens elect 650 MPs to the House of Commons. The leader of the party with most MPs becomes Prime Minister, invited by the Monarch."),
        (("brazil",), "🇧🇷 Brazil has compulsory voting for ages 18–70. The President is elected via a two-round majority system. Brazil pioneered fully electronic voting in 1996 — one of the world's most advanced systems."),
        (("eu", "europe"), "🇪🇺 EU citizens elect 720 Members of European Parliament (MEPs) every 5 years. Each of the 27 member states uses proportional representation. The Parliament co-legislates EU law."),
    ]

    for keywords, response in responses:
        if any(keyword in msg_lower for keyword in keywords):
            return response

    return "I'm ElectIQ, your election education guide! Ask me about voting systems, timelines, or the election process in India, USA, UK, EU, Brazil, and more. 🗳️"


def fallback_response(message: str) -> str:
    """Provide fallback responses when Gemini is unavailable.

    Args:
        message: User prompt to match against election topics.

    Returns:
        A topic-specific fallback response.
    """

    return _build_fallback_response(message)


if __name__ == "__main__":
    logger.info("Starting ElectIQ server on %s:%s", config.HOST, config.PORT)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
