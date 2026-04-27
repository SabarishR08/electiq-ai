"""Quiz routes for country-specific election knowledge checks.

The blueprint builds quiz questions from the static country dataset and uses
Gemini opportunistically for richer wording when available.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from routes.elections import _load_elections_data
from services.exceptions import ValidationError
from services.gemini_service import get_gemini_service
from services.security_service import get_security_service, require_json_fields

logger = logging.getLogger(__name__)

quiz_bp = Blueprint("quiz", __name__)
limiter = Limiter(key_func=get_remote_address)
security_service = get_security_service()


def _error_response(message: str, status_code: int) -> tuple[dict[str, Any], int]:
    """Build a JSON error response."""

    return {"error": message}, status_code


def _validate_quiz_difficulty(difficulty: str) -> str:
    """Validate and normalize quiz difficulty."""

    normalized_difficulty = (difficulty or "").strip().lower()
    if normalized_difficulty not in config.QUIZ_DIFFICULTIES:
        raise ValidationError("Unsupported quiz difficulty")
    return normalized_difficulty


def _sanitize_quiz_question(question: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a quiz question payload."""

    return {
        "id": int(question.get("id", 0)),
        "question": security_service.sanitize_html(str(question.get("question", "")), 500),
        "options": [security_service.sanitize_html(str(option), 200) for option in question.get("options", [])[: config.QUIZ_MAX_ANSWER_OPTIONS]],
        "correct": int(question.get("correct", 0)),
        "explanation": security_service.sanitize_html(str(question.get("explanation", "")), 500),
    }


def _build_base_questions(country_data: dict[str, Any], difficulty: str) -> list[dict[str, Any]]:
    """Build deterministic quiz questions from static country data."""

    name = country_data.get("name", "this country")
    system = country_data.get("system", "the electoral system")
    body = country_data.get("body", "the election authority")
    frequency = country_data.get("frequency", "the standard election cycle")
    voters = country_data.get("voters", "the electorate")
    facts = country_data.get("facts", [])
    first_fact = facts[0] if facts else f"{name} has a unique election system."

    question_templates = [
        {
            "question": f"Which body oversees elections in {name}?",
            "options": [body, "The Supreme Court", "The national police", "The finance ministry"],
            "correct": 0,
            "explanation": f"{body} is the primary electoral authority in {name}.",
        },
        {
            "question": f"How often are major elections held in {name}?",
            "options": [frequency, "Every year", "Every 10 years", "Only once per decade"],
            "correct": 0,
            "explanation": f"According to the country profile, elections in {name} follow this schedule: {frequency}.",
        },
        {
            "question": f"What electoral system does {name} use?",
            "options": [system, "Sortition", "Random selection", "No formal system"],
            "correct": 0,
            "explanation": f"The country profile identifies {system} as the main electoral system.",
        },
        {
            "question": f"Approximately how many voters are represented in {name}?",
            "options": [voters, "Under 1 million", "Under 10 million", "No registered voters"],
            "correct": 0,
            "explanation": f"The country profile lists about {voters} eligible voters.",
        },
        {
            "question": f"Which statement best matches a key fact about {name}?",
            "options": [first_fact, "The election system changes every month", "Voting is secret and random", "There are no election laws"],
            "correct": 0,
            "explanation": f"A key fact about {name} is: {first_fact}",
        },
    ]

    if difficulty == "intermediate":
        question_templates[0]["question"] = f"Which institution manages voter administration and polling in {name}?"
        question_templates[1]["question"] = f"What is the usual election cycle for major national elections in {name}?"
    elif difficulty == "advanced":
        question_templates[2]["question"] = f"Which electoral model most accurately describes the system used in {name}?"
        question_templates[4]["question"] = f"Which of the following is a verifiable election fact about {name}?"

    return question_templates


def _generate_questions_with_gemini(country_data: dict[str, Any], difficulty: str) -> Optional[list[dict[str, Any]]]:
    """Ask Gemini to generate quiz questions and parse a JSON response."""

    gemini_service = get_gemini_service()
    if not gemini_service.is_available():
        return None

    prompt = (
        "Generate 5 multiple-choice election quiz questions as strict JSON. "
        f"Country: {country_data.get('name')}. Difficulty: {difficulty}. "
        "Return an array of objects with keys: id, question, options, correct, explanation."
    )
    response_text = gemini_service.generate_response(prompt, history=None, temperature=0.2)
    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, list) and len(parsed) == config.QUIZ_QUESTION_COUNT:
            return [question for question in parsed if isinstance(question, dict)]
    except json.JSONDecodeError:
        logger.debug("Gemini quiz response was not valid JSON")

    return None


def _build_quiz_questions(country_id: str, difficulty: str) -> list[dict[str, Any]]:
    """Build sanitized quiz questions for a country and difficulty."""

    country_data = _load_elections_data().get(country_id, {})
    generated_questions = _generate_questions_with_gemini(country_data, difficulty)
    base_questions = generated_questions or _build_base_questions(country_data, difficulty)

    questions = []
    for index, question in enumerate(base_questions[: config.QUIZ_QUESTION_COUNT], 1):
        question_payload = dict(question)
        question_payload["id"] = index
        questions.append(_sanitize_quiz_question(question_payload))

    return questions


def _score_quiz(country_id: str, answers: list[dict[str, Any]], difficulty: str) -> tuple[int, list[dict[str, Any]]]:
    """Score submitted quiz answers against the generated question set."""

    questions = _build_quiz_questions(country_id, difficulty)
    answer_map = {
        int(answer.get("id", 0)): int(answer.get("selected", -1))
        for answer in answers
        if isinstance(answer, dict)
    }

    results: list[dict[str, Any]] = []
    score = 0
    for question in questions:
        selected = answer_map.get(question["id"], -1)
        correct = selected == question["correct"]
        if correct:
            score += 1

        results.append({
            "id": question["id"],
            "correct": correct,
            "explanation": question["explanation"],
        })

    return score, results


@quiz_bp.route("/quiz/generate", methods=["POST"])
@limiter.limit(f"{config.QUIZ_REQUESTS_PER_MINUTE}/minute")
@require_json_fields("country", "difficulty")
def generate_quiz() -> tuple[dict[str, Any], int]:
    """Generate quiz questions for a country."""

    payload = request.get_json(silent=True) or {}
    try:
        country_id = security_service.validate_country_id(str(payload.get("country", "")))
        difficulty = _validate_quiz_difficulty(str(payload.get("difficulty", "")))
    except ValidationError as exc:
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)

    questions = _build_quiz_questions(country_id, difficulty)
    return jsonify({
        "questions": questions,
        "country": country_id,
        "difficulty": difficulty,
    }), config.HTTP_OK


@quiz_bp.route("/quiz/submit", methods=["POST"])
@limiter.limit(f"{config.QUIZ_REQUESTS_PER_MINUTE}/minute")
@require_json_fields("country", "answers")
def submit_quiz() -> tuple[dict[str, Any], int]:
    """Score a submitted quiz attempt."""

    payload = request.get_json(silent=True) or {}
    try:
        country_id = security_service.validate_country_id(str(payload.get("country", "")))
        answers = payload.get("answers", [])
        if not isinstance(answers, list):
            raise ValidationError("Invalid answers payload")

        difficulty = _validate_quiz_difficulty(str(payload.get("difficulty", "beginner")))
    except ValidationError as exc:
        return _error_response(str(exc), config.HTTP_BAD_REQUEST)

    score, results = _score_quiz(country_id, answers, difficulty)
    total = len(results)
    percentage = int((score / total) * 100) if total else 0
    return jsonify({
        "score": score,
        "total": total,
        "percentage": percentage,
        "results": results,
    }), config.HTTP_OK


@quiz_bp.route("/quiz/countries", methods=["GET"])
@limiter.limit(f"{config.QUIZ_REQUESTS_PER_MINUTE}/minute")
def list_quiz_countries() -> tuple[dict[str, Any], int]:
    """List countries available for quiz generation."""

    elections_data = _load_elections_data()
    countries = [
        {
            "id": country_id,
            "name": country_data.get("name"),
            "flag": country_data.get("flag"),
            "system": country_data.get("system"),
        }
        for country_id, country_data in elections_data.items()
    ]
    return jsonify({"countries": countries}), config.HTTP_OK