# Electiq Ai

![License](https://img.shields.io/badge/license-MIT-green) ![Language](https://img.shields.io/badge/language-Python-informational) ![Docker](https://img.shields.io/badge/docker-ready-2496ed)


## 📌 Overview

AI-powered election education assistant — interactive guides, timelines & multilingual Q&A built with Gemini, Vertex AI, Firebase, Cloud Translate, and Cloud Run.

## 🏗️ Architecture

```text
Browser / UI
     │   HTTP
     ▼
Flask app
     │
     └──▶ External services — Google Gemini
```

## 🧰 Tech Stack

- **Language:** Python
- **Backend:** Flask
- **Integrations:** Google Gemini
- **Deployment:** Docker container

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Docker (optional, for container runs)

### 1. Clone

```bash
git clone https://github.com/SabarishR08/electiq-ai.git
cd electiq-ai
```

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env   # then fill in values
```

Environment variables used: `SECRET_KEY`, `DEBUG`, `TESTING`, `PORT`, `HOST`, `GEMINI_API_KEY`, `GOOGLE_TRANSLATE_ENABLED`, `GOOGLE_CLOUD_PROJECT`, `VERTEX_LOCATION`, `VERTEX_GROUNDING_ENABLED`, `FIREBASE_ENABLED`, `FIREBASE_CREDENTIALS_PATH`, `CHAT_REQUESTS_PER_MINUTE`, `TRANSLATE_REQUESTS_PER_MINUTE`, `GENERAL_REQUESTS_PER_MINUTE`, `LOG_LEVEL`.

External services involved: Google Gemini.

### 4. Run

```bash
python app.py
```

### (Alternative) Run with Docker

```bash
docker build -t electiq-ai .
docker run -p 5000:5000 electiq-ai
```


---

ElectIQ is a production-focused election education platform built with Flask. It combines structured country data, AI-assisted explanations, translation tools, glossary lookups, quizzes, comparison views, and lightweight analytics in a single deployment.

The live Cloud Run URL remains:
https://electiq-ai-253750832620.us-central1.run.app

## What It Does

ElectIQ helps users explore how elections work across India, the USA, the UK, the EU, and Brazil. The app now includes:

- Country profiles, timelines, voting steps, and facts
- AI chat with optional history summarization and feedback capture
- Grounded responses through Vertex-backed tooling when available
- Translation and language detection endpoints
- Glossary search and contextual explanations
- Side-by-side country comparison
- Quiz generation and scoring
- In-memory analytics for popular-country tracking
- Request tracing, security headers, and request size protection

## Architecture

The application is split into thin blueprints and service wrappers so each layer stays focused:

- `app.py` wires the Flask app, security headers, request IDs, and blueprint registration
- `routes/` contains the HTTP surface area
- `services/` wraps Gemini, Firebase, Translate, Vertex, and security utilities
- `data/` stores the static election and glossary JSON datasets
- `tests/` covers routes, services, accessibility, security, and data integrity

## API Surface

Core endpoints include:

- `GET /health`
- `GET /api/elections`
- `GET /api/elections/<country_id>`
- `GET /api/elections/<country_id>/timeline`
- `GET /api/elections/<country_id>/voting-steps`
- `GET /api/elections/<country_id>/facts`
- `GET /api/elections/search?q=...`
- `POST /api/chat`
- `POST /api/chat/grounded`
- `POST /api/chat/feedback`
- `GET /api/chat/suggestions?country=...`
- `GET /api/chat/history/<session_id>`
- `POST /api/translate`
- `POST /api/translate/detect`
- `POST /translate/batch`
- `GET /translate/supported`
- `GET /api/languages`
- `GET /api/glossary`
- `GET /api/glossary/<term_slug>`
- `GET /api/glossary/search?q=...`
- `POST /api/glossary/explain`
- `POST /api/quiz/generate`
- `POST /api/quiz/submit`
- `GET /api/quiz/countries`
- `GET /api/compare?countries=india,usa`
- `GET /api/compare/metrics`
- `POST /api/analytics/track`
- `GET /api/analytics/popular`

## Security

ElectIQ now applies a layered security baseline:

- HTML sanitization and injection detection for user input
- Rate limiting on chat, translation, quiz, glossary, comparison, and analytics routes
- Request IDs on every response for traceability
- JSON request validation helpers for required fields
- Security headers for content type, framing, referrer policy, CSP, and transport policy
- `MAX_CONTENT_LENGTH` protection with a JSON 413 handler

## Technology

- Flask 3.1.0
- Google Gemini
- Google Cloud Translate
- Firebase Admin / Firestore
- Vertex AI Search / grounding helpers
- Flask-Limiter
- pytest

## Local Development

Install dependencies and start the app:

```bash
pip install -r requirements.txt
python app.py
```

The application listens on the host and port defined in `config.py`.

## Testing

Run the full test suite:

```bash
pytest tests -v
```

Current validated status: 319 tests passing.

## Deployment

Deploy to Cloud Run with the existing service name and URL:

```bash
gcloud run deploy electiq-ai \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

Health check:

https://electiq-ai-253750832620.us-central1.run.app/health

## Environment Variables

Common configuration values:

- `GEMINI_API_KEY`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_TRANSLATE_ENABLED`
- `FIREBASE_ENABLED`
- `FIREBASE_CREDENTIALS_PATH`
- `VERTEX_GROUNDING_ENABLED`
- `RATELIMIT_STORAGE_URI`

---

## 📄 License

[MIT](LICENSE) — © 2026 Sabarish R.
