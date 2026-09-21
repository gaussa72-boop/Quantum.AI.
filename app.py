import os
import uuid
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI

app = Flask(__name__)

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "high").strip().lower()
WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "true").strip().lower() == "true"
AI_ENABLED = os.getenv("AI_ENABLED", "true").strip().lower() == "true"
MAX_HISTORY = max(4, min(int(os.getenv("MAX_HISTORY_MESSAGES", "20")), 40))
MAX_INPUT_CHARS = max(1000, min(int(os.getenv("MAX_INPUT_CHARS", "12000")), 30000))
RATE_LIMIT_PER_MINUTE = max(5, min(int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")), 120))

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
- Wenn eine Aufgabe mehrdeutig ist, stelle nur dann eine Rückfrage, wenn sie wirklich erforderlich ist.
- Antworte in der Sprache des Nutzers.
"""

sessions = {}
sessions_lock = Lock()
rate = defaultdict(deque)
rate_lock = Lock()

def clean_history(history):
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

def get_session(session_id, supplied_history=None):
    sid = str(session_id or "").strip()[:120] or str(uuid.uuid4())
    with sessions_lock:
        if supplied_history is not None and sid not in sessions:
            sessions[sid] = clean_history(supplied_history)
        history = list(sessions.get(sid, []))
    return sid, history

def allowed(ip):
    now = monotonic()
    with rate_lock:
        q = rate[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MINUTE:
            return False
        q.append(now)
        return True

@app.get("/")
def home():
    return send_from_directory("frontend", "index.html")

@app.get("/health")
@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "project": "Quantum.AI",
        "runtime": "python",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "web_search": WEB_SEARCH,
        "ai_enabled": AI_ENABLED,
        "openai_configured": bool(client and AI_ENABLED),
    })

@app.post("/api/reset")
def reset():
    data = request.get_json(silent=True) or {}
    sid = str(data.get("session_id") or "").strip()[:120]
    if sid:
        with sessions_lock:
            sessions.pop(sid, None)
    return jsonify({"ok": True})

@app.post("/api/chat")
@app.post("/chat")
def chat():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    if not allowed(ip):
        return jsonify({"ok": False, "error": "Zu viele Anfragen. Bitte kurz warten."}), 429

    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message is required"}), 400
    if len(message) > MAX_INPUT_CHARS:
        return jsonify({"ok": False, "error": f"Nachricht zu lang (max. {MAX_INPUT_CHARS} Zeichen)."}), 413
    if not AI_ENABLED:
        return jsonify({"ok": False, "error": "Quantum.AI ist deaktiviert (AI_ENABLED=false)."}), 503
    if not client:
        return jsonify({"ok": False, "error": "OPENAI_API_KEY ist auf Render nicht gesetzt."}), 503

    session_id, history = get_session(data.get("session_id"), data.get("history"))
    input_items = (history + [{"role": "user", "content": message}])[-MAX_HISTORY:]

    kwargs = {
        "model": MODEL,
        "instructions": SYSTEM,
        "input": input_items,
        "store": False,
    }
    if WEB_SEARCH:
        kwargs["tools"] = [{"type": "web_search", "search_context_size": "medium"}]
        kwargs["tool_choice"] = "auto"
    if REASONING_EFFORT in {"low", "medium", "high", "xhigh", "max"}:
        kwargs["reasoning"] = {"effort": REASONING_EFFORT}

    try:
        response = client.responses.create(**kwargs)
        answer = (response.output_text or "").strip() or "Ich konnte diesmal keine Textantwort erzeugen. Bitte versuche es erneut."
        final_history = (input_items + [{"role": "assistant", "content": answer}])[-MAX_HISTORY:]
        with sessions_lock:
            sessions[session_id] = final_history
        return jsonify({"ok": True, "response": answer, "answer": answer, "model": MODEL, "session_id": session_id})
    except Exception:
        app.logger.exception("Quantum.AI API error")
        return jsonify({"ok": False, "error": "Die KI-Schnittstelle ist momentan nicht erreichbar. Prüfe OPENAI_API_KEY, Modellzugriff, Guthaben und Render-Logs."}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
