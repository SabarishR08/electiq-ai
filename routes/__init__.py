"""Public route exports for the ElectIQ application."""

from routes.analytics import analytics_bp
from routes.chat import chat_bp
from routes.compare import compare_bp
from routes.elections import elections_bp
from routes.glossary import glossary_bp
from routes.health import health_bp
from routes.quiz import quiz_bp
from routes.translate import translate_bp

__all__ = ["elections_bp", "chat_bp", "translate_bp", "health_bp", "quiz_bp", "glossary_bp", "compare_bp", "analytics_bp"]
