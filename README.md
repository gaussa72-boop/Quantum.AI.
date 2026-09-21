# Quantum.AI

Produktionsfähige Flask-Web-KI für Render.

## Stack
- Python 3.13
- Flask + Gunicorn
- OpenAI Responses API
- optionale Websuche
- persistente Browser-Sitzung über localStorage + session_id
- Healthcheck unter /health

## Render
Build: `pip install --upgrade pip && pip install -r requirements.txt`

Start: `gunicorn --bind 0.0.0.0:$PORT app:app`

Erforderlich:
- `OPENAI_API_KEY`

Optional:
- `OPENAI_MODEL` = `gpt-5.6`
- `OPENAI_REASONING_EFFORT` = `high`
- `ENABLE_WEB_SEARCH` = `true`
- `AI_ENABLED` = `true`

API-Schlüssel werden ausschließlich in Render Environment Variables gespeichert.
