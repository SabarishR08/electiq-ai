"""Health check route for load balancers and monitoring.

The endpoint is intentionally simple and returns a stable JSON payload.
"""

import logging

from flask import Blueprint, jsonify

import config

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check() -> tuple[dict, int]:
    """Return the service health status payload.

    Returns:
        A JSON payload describing the API service status.
    """

    return jsonify({
        "status": "ok",
        "service": config.SERVICE_NAME,
        "version": config.SERVICE_VERSION,
        "component": "api-server",
    }), config.HTTP_OK


@health_bp.route("/api/google-services", methods=["GET"])
def google_services() -> tuple[dict, int]:
    """Return the Google service registry used by the application."""

    return jsonify({"google_services": config.GOOGLE_SERVICES}), config.HTTP_OK
