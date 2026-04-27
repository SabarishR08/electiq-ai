"""Application configuration constants for ElectIQ.

The module centralizes environment reads and shared constants used by routes,
services, and app startup. It intentionally contains no business logic.
"""

import os
from typing import Final, Optional

# === API Configuration ===
SECRET_KEY: str = os.environ.get("SECRET_KEY", "electiq-dev-key-2026-change-in-production")
DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"
TESTING: bool = os.environ.get("TESTING", "false").lower() == "true"
PORT: int = int(os.environ.get("PORT", 8080))
HOST: str = os.environ.get("HOST", "0.0.0.0")
SERVICE_NAME: str = "ElectIQ"
SERVICE_VERSION: str = "1.0.0"
DEFAULT_CLOUD_RUN_URL: str = "https://electiq-ai-253750832620.us-central1.run.app"
MAX_CONTENT_LENGTH_BYTES: int = 1 * 1024 * 1024
REQUEST_ID_HEADER: str = "X-Request-ID"

GOOGLE_SERVICES: dict[str, dict[str, object]] = {
    "gemini": {
        "name": "Google Gemini 1.5 Flash",
        "package": "google-generativeai",
        "purpose": "AI-powered election Q&A chatbot",
        "enabled": True,
    },
    "translate": {
        "name": "Google Cloud Translate v2",
        "package": "google-cloud-translate",
        "purpose": "8-language content translation",
        "enabled": True,
    },
    "vertex_ai": {
        "name": "Vertex AI + Grounding",
        "package": "google-cloud-aiplatform",
        "purpose": "Grounded election fact verification",
        "enabled": True,
    },
    "firebase": {
        "name": "Firebase Admin + Firestore",
        "package": "firebase-admin",
        "purpose": "Chat session history storage",
        "enabled": True,
    },
    "bigquery": {
        "name": "Google BigQuery",
        "package": "google-cloud-bigquery",
        "purpose": "Election query analytics and usage tracking",
        "enabled": True,
    },
    "cloud_storage": {
        "name": "Google Cloud Storage",
        "package": "google-cloud-storage",
        "purpose": "AI response caching and election data exports",
        "enabled": True,
    },
    "cloud_run": {
        "name": "Google Cloud Run",
        "package": "N/A - deployment platform",
        "purpose": "Serverless container deployment with auto-scaling",
        "enabled": True,
    },
}

# === Google AI Services ===
GEMINI_API_KEY: Optional[str] = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL: str = "gemini-1.5-flash"
SYSTEM_PROMPT: str = (
    "You are ElectIQ, a friendly and knowledgeable election education assistant. "
    "You help people understand electoral systems, voting processes, timelines, and democratic participation worldwide.\n\n"
    "You have deep knowledge about elections in India, the USA, UK, EU, Brazil, and other countries.\n\n"
    "Be concise, factual, and engaging. Use emojis sparingly. If asked about a specific country, provide accurate details "
    "about their electoral system. Always encourage civic participation.\n\n"
    "If asked something outside elections/democracy/voting, politely redirect to your area of expertise.\n\n"
    "Keep answers under 200 words unless complex detail is requested."
)
TRANSLATE_ENABLED: bool = os.environ.get("GOOGLE_TRANSLATE_ENABLED", "false").lower() == "true"
VERTEX_PROJECT_ID: Optional[str] = os.environ.get("GOOGLE_CLOUD_PROJECT")
VERTEX_LOCATION: str = os.environ.get("VERTEX_LOCATION", "us-central1")
VERTEX_GROUNDING_ENABLED: bool = os.environ.get("VERTEX_GROUNDING_ENABLED", "false").lower() == "true"
FIREBASE_ENABLED: bool = os.environ.get("FIREBASE_ENABLED", "false").lower() == "true"
FIREBASE_CREDENTIALS_PATH: Optional[str] = os.environ.get("FIREBASE_CREDENTIALS_PATH")
FIRESTORE_CHAT_COLLECTION: str = os.environ.get("FIRESTORE_CHAT_COLLECTION", "chat_sessions")

# === Rate Limiting ===
RATELIMIT_ENABLED: bool = True
RATELIMIT_STORAGE_URI: str = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
CHAT_REQUESTS_PER_MINUTE: int = 20
TRANSLATE_REQUESTS_PER_MINUTE: int = 30
GENERAL_REQUESTS_PER_MINUTE: int = 60
QUIZ_REQUESTS_PER_MINUTE: int = 10
ANALYTICS_REQUESTS_PER_MINUTE: int = 60
GLOSSARY_REQUESTS_PER_MINUTE: int = 30
COMPARE_REQUESTS_PER_MINUTE: int = 30

# === Input Validation ===
MIN_MESSAGE_LENGTH: int = 1
MAX_MESSAGE_LENGTH: int = 500
MAX_TEXT_TRANSLATION_LENGTH: int = 5000
MAX_SESSION_ID_LENGTH: int = 100
CHAT_HISTORY_MAX_LENGTH: int = 8
CHAT_SUMMARY_TRIGGER_MESSAGES: int = 10
CHAT_SUMMARY_RECENT_MESSAGES: int = 6
RESPONSE_TIMEOUT_SECONDS: int = 60
CACHE_TTL_SECONDS: int = 3600
SUPPORTED_LANGUAGES: list[str] = ["en", "hi", "ta", "es", "fr", "de", "pt", "ar"]
ELECTION_COUNTRY_IDS: list[str] = ["india", "usa", "uk", "eu", "brazil"]
ALLOWED_COUNTRIES: list[str] = ELECTION_COUNTRY_IDS
VALID_COUNTRY_IDS: list[str] = ELECTION_COUNTRY_IDS
QUIZ_DIFFICULTIES: list[str] = ["beginner", "intermediate", "advanced"]
QUIZ_QUESTION_COUNT: int = 5
QUIZ_MAX_ANSWER_OPTIONS: int = 4
QUIZ_MAX_COUNTRIES: int = 5
BATCH_TRANSLATION_MAX_ITEMS: int = 10
COMPARE_MAX_COUNTRIES: int = 4
GLOSSARY_SEARCH_LIMIT: int = 10
ANALYTICS_TOP_COUNTRIES_LIMIT: int = 10
STATIC_ESTIMATED_STEP_MINUTES: int = 3
API_SEARCH_MAX_RESULTS: int = 10

# === Supported Languages ===
DEFAULT_SOURCE_LANGUAGE: str = "en"
SUPPORTED_LANGUAGE_DETAILS: dict[str, dict[str, object]] = {
    "en": {"name": "English", "native": "English", "rtl": False},
    "hi": {"name": "Hindi", "native": "हिन्दी", "rtl": False},
    "ta": {"name": "Tamil", "native": "தமிழ்", "rtl": False},
    "es": {"name": "Spanish", "native": "Español", "rtl": False},
    "fr": {"name": "French", "native": "Français", "rtl": False},
    "de": {"name": "German", "native": "Deutsch", "rtl": False},
    "pt": {"name": "Portuguese", "native": "Português", "rtl": False},
    "ar": {"name": "Arabic", "native": "العربية", "rtl": True},
}

# === Election Countries ===
COUNTRY_INDIA: str = "india"
COUNTRY_USA: str = "usa"
COUNTRY_UK: str = "uk"
COUNTRY_EU: str = "eu"
COUNTRY_BRAZIL: str = "brazil"

# === Security Headers ===
HEADER_CONTENT_TYPE_OPTIONS: str = "X-Content-Type-Options"
HEADER_FRAME_OPTIONS: str = "X-Frame-Options"
HEADER_XSS_PROTECTION: str = "X-XSS-Protection"
HEADER_REFERRER_POLICY: str = "Referrer-Policy"
HEADER_CONTENT_SECURITY_POLICY: str = "Content-Security-Policy"
HEADER_PERMISSIONS_POLICY: str = "Permissions-Policy"
HEADER_CROSS_ORIGIN_OPENER_POLICY: str = "Cross-Origin-Opener-Policy"
HEADER_CROSS_ORIGIN_RESOURCE_POLICY: str = "Cross-Origin-Resource-Policy"
HEADER_STRICT_TRANSPORT_SECURITY: str = "Strict-Transport-Security"
HEADER_CACHE_CONTROL: str = "Cache-Control"
HEADER_VALUE_NOSNIFF: str = "nosniff"
HEADER_VALUE_SAMEORIGIN: str = "SAMEORIGIN"
HEADER_VALUE_XSS_BLOCK: str = "1; mode=block"
HEADER_VALUE_STRICT_REFERRER_POLICY: str = "strict-origin-when-cross-origin"
HEADER_VALUE_PERMISSIONS_POLICY: str = (
    "camera=(), microphone=(), geolocation=()"
)
HEADER_VALUE_CROSS_ORIGIN_OPENER_POLICY: str = "same-origin"
HEADER_VALUE_CROSS_ORIGIN_RESOURCE_POLICY: str = "same-origin"
HEADER_VALUE_STRICT_TRANSPORT_SECURITY: str = "max-age=31536000; includeSubDomains"
HEADER_VALUE_NO_STORE: str = "no-store"

CORS_HEADERS: dict[str, str] = {
    HEADER_CONTENT_TYPE_OPTIONS: HEADER_VALUE_NOSNIFF,
    HEADER_FRAME_OPTIONS: HEADER_VALUE_SAMEORIGIN,
    HEADER_XSS_PROTECTION: HEADER_VALUE_XSS_BLOCK,
    HEADER_REFERRER_POLICY: HEADER_VALUE_STRICT_REFERRER_POLICY,
}

CSP_HEADER: str = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://generativelanguage.googleapis.com https://translation.googleapis.com; "
    "frame-ancestors 'none';"
)

# === Data Files ===
DATA_DIR: str = os.path.join(os.path.dirname(__file__), "data")
ELECTIONS_DATA_FILE: str = os.path.join(DATA_DIR, "elections.json")
GLOSSARY_DATA_FILE: str = os.path.join(DATA_DIR, "glossary.json")

# === Logging ===
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# === Error Messages ===
ERROR_CONTENT_TYPE_JSON: str = "Content-Type must be application/json"
ERROR_MESSAGE_REQUIRED: str = "Message is required"
ERROR_TRANSLATION_TEXT_REQUIRED: str = "Text is required"
ERROR_COUNTRY_NOT_FOUND: str = "Country not found"
ERROR_FAILED_RESPONSE: str = "Failed to generate response"
ERROR_FAILED_TRANSLATION: str = "Failed to translate text"
ERROR_FAILED_HISTORY: str = "Failed to retrieve chat history"
ERROR_FAILED_GLOSSARY: str = "Failed to fetch glossary"
ERROR_FAILED_LANGUAGE_DETECTION: str = "Failed to detect language"
ERROR_INVALID_SESSION_ID: str = "Invalid session_id"
ERROR_REQUEST_TOO_LARGE: str = "Request too large"
ERROR_MISSING_REQUIRED_FIELDS: str = "Missing required fields"

# === Content Policy ===
PROFANITY_WORDS: list[str] = ["fuck", "shit", "bitch", "asshole", "bastard"]
PERSONAL_VOTER_PATTERNS: list[str] = [
    "personal voter",
    "voter id number",
    "my voter id",
    "voter registration details",
    "who am i registered with",
    "polling station for me",
]

# === HTTP Status Codes ===
HTTP_OK: int = 200
HTTP_BAD_REQUEST: int = 400
HTTP_NOT_FOUND: int = 404
HTTP_REQUEST_ENTITY_TOO_LARGE: int = 413
HTTP_SERVICE_UNAVAILABLE: int = 503
HTTP_INTERNAL_SERVER_ERROR: int = 500

# Backwards-compatible aliases for existing call sites.
DEFAULT_LANGUAGE: Final[str] = DEFAULT_SOURCE_LANGUAGE
