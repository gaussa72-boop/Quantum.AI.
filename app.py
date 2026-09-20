import os
import uuid
from threading import Lock

from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI

app = Flask(__name__)

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "high").strip().lower()
WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "true").strip().lower() == "true"
AI_ENABLED = os.getenv("AI_ENABLED", "true").strip().lower() == "true"
MAX_HISTORY = max(4, min(int(os.getenv("MAX_HISTORY_MESSAGES", "20")), 40))
MAX_INPUT_CHARS = max(1000, min(int(os.getenv("MAX_INPUT_CHARS", "12000")), 30000))

API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
client = OpenAI(api_key=API_KEY) if API_KEY else None

SYSTEM = """Du bist Quantum.AI, ein leistungsfähiger allgemeiner KI-Assistent für Recherche,
Analyse, Programmierung, Mathematik, Schreiben und Projektarbeit.

Arbeitsweise:
- Verstehe zuerst die konkrete Aufgabe und beantworte sie direkt.
- Arbeite strukturiert, präzise und nachvollziehbar.
- Trenne gesicherte Fakten, Annahmen und Unsicherheit.
- Bei aktuellen oder veränderlichen Informationen nutze die Websuche, wenn sie aktiviert ist.
- Erfinde niemals Quellen, Daten, Ergebnisse oder ausgeführte Aktionen.
- Bei Code: liefere funktionsfähige, wartbare Lösungen und berücksichtige vorhandenen Kontext.
- Wenn eine Aufgabe mehrdeutig ist, stelle nur dann eine Rückfrage, wenn sie für eine korrekte Lösung wirklich erforderlich ist.
- Antworte in der Sprache des Nutzers.
"""

sessions = {}
sessions_lock = Lock()


def _clean_history(history):
    if not isinstance(history, list):
        return []
    cleaned = []
    for item in history[-MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            cleaned.append({"role": role, "content": content[:MAX_INPUT_CHARS]})
    return cleaned


def _session_history(session_id, supplied_history=None):
    sid = str(session_id or "").strip()[:120]
    if not sid:
        sid = str(uuid.uuid4())
    with sessions_lock:
        if supplied_history is not None and sid not in sessions:
            sessions[sid] = _clean_history(supplied_history)
        history = list(sessions.get(sid, []))
    return sid, history


@app.get("/")
def home():
    return send_from_directory("frontend", "index.html")


@app.get("/engine")
def engine():
    return send_from_directory(".", "game_engine.html")


@app.get("/game_engine.js")
def engine_js():
    return send_from_directory(".", "game_engine.js")


@app.get("/health")
@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "project": "Quantum.AI.",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "web_search": WEB_SEARCH,
        "ai_enabled": AI_ENABLED,
        "openai_configured": bool(client and AI_ENABLED),
        "sessions": len(sessions),
    })


@app.post("/api/reset")
def reset():
    data = request.get_json(silent=True) or {}
    sid = str(data.get("session_id") or "").strip()[:120]
    if sid:
        with sessions_lock:
            sessions.pop(sid, None)
    return jsonify({"ok": True})


@app.post("/chat")
@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message is required"}), 400
    if len(message) > MAX_INPUT_CHARS:
        return jsonify({"ok": False, "error": f"Nachricht zu lang (max. {MAX_INPUT_CHARS} Zeichen)."}), 400
    if not AI_ENABLED:
        return jsonify({"ok": False, "error": "Quantum.AI ist deaktiviert (AI_ENABLED=false)."}), 503
    if not client:
        return jsonify({"ok": False, "error": "OPENAI_API_KEY ist auf dem Server nicht konfiguriert."}), 503

    session_id, history = _session_history(data.get("session_id"), data.get("history"))

    next_history = history + [{"role": "user", "content": message}]
    input_items = next_history[-MAX_HISTORY:]

    tools = []
    if WEB_SEARCH:
        tools.append({"type": "web_search", "search_context_size": "medium"})

    try:
        kwargs = {
            "model": MODEL,
            "instructions": SYSTEM,
            "input": input_items,
            "tools": tools,
            "tool_choice": "auto" if tools else "none",
            "store": False,
        }
        if REASONING_EFFORT in {"low", "medium", "high"}:
            kwargs["reasoning"] = {"effort": REASONING_EFFORT}

        response = client.responses.create(**kwargs)
        answer = (response.output_text or "").strip()

        if not answer:
            answer = "Ich konnte diesmal keine Textantwort erzeugen. Bitte versuche es erneut."

        final_history = (next_history + [{"role": "assistant", "content": answer}])[-MAX_HISTORY:]
        with sessions_lock:
            sessions[session_id] = final_history

        return jsonify({
            "ok": True,
            "response": answer,
            "answer": answer,
            "model": MODEL,
            "session_id": session_id,
        })

    except Exception as exc:
        app.logger.exception("Quantum.AI API error")
        # Do not expose API keys or raw provider internals to the browser.
        return jsonify({
            "ok": False,
            "error": "Die KI-Schnittstelle ist momentan nicht erreichbar. Prüfe API-Key, OpenAI-Guthaben und Render-Logs."
        }), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
