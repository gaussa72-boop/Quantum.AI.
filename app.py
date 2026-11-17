import os
import uuid
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI

app = Flask(__name__)

ALLOWED_FRONTEND_ORIGINS = {"https://quantumai-chat.onrender.com"}

@app.after_request
def cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_FRONTEND_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response

# SECURITY HARDENING
_SEC_RATE_LIMIT={}
from time import monotonic
@app.before_request
def _sec_before():
    if request.content_length and request.content_length>1048576:return jsonify(error="Request too large."),413
    if request.path.startswith("/.git/") or request.path.startswith("/.env"):return jsonify(error="Not Found."),404
    ip=request.remote_addr or "unknown";now=monotonic();b=_SEC_RATE_LIMIT.setdefault(ip,[]);b[:]=[t for t in b if now-t<60];limit=30 if request.method in {"POST","PUT","PATCH","DELETE"} else 120
    if len(b)>=limit:return jsonify(error="Too many requests. Please try again later."),429
    b.append(now)
@app.after_request
def _sec_headers(response):
    response.headers.setdefault("X-Content-Type-Options","nosniff");response.headers.setdefault("X-Frame-Options","DENY");response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin");response.headers.setdefault("Permissions-Policy","camera=(), microphone=(), geolocation=()");response.headers.setdefault("Cross-Origin-Opener-Policy","same-origin");response.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains");response.headers.pop("Server",None);return response




OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "high").strip().lower()
WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "true").strip().lower() == "true"
AI_ENABLED = os.getenv("AI_ENABLED", "true").strip().lower() == "true"
MAX_HISTORY = max(4, min(int(os.getenv("MAX_HISTORY_MESSAGES", "20")), 40))
MAX_INPUT_CHARS = max(1000, min(int(os.getenv("MAX_INPUT_CHARS", "12000")), 30000))
RATE_LIMIT_PER_MINUTE = max(5, min(int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")), 120))

client = OpenAI(api_key=API_KEY) if API_KEY else None
router_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1") if OPENROUTER_API_KEY else None
if AI_PROVIDER == "openrouter" and router_client:
    ACTIVE_PROVIDER, ACTIVE_CLIENT, MODEL = "openrouter", router_client, OPENROUTER_MODEL
elif client:
    ACTIVE_PROVIDER, ACTIVE_CLIENT, MODEL = "openai", client, OPENAI_MODEL
elif router_client:
    ACTIVE_PROVIDER, ACTIVE_CLIENT, MODEL = "openrouter", router_client, OPENROUTER_MODEL
else:
    ACTIVE_PROVIDER, ACTIVE_CLIENT, MODEL = AI_PROVIDER, None, OPENAI_MODEL

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



def load_author_research_context():
    """Load the author's curated research concepts without changing this agent's identity."""
    from pathlib import Path
    try:
        return Path(__file__).with_name("research").joinpath("ADRIANO_IDEENWISSEN.md").read_text(encoding="utf-8")
    except OSError:
        app.logger.warning("Author research knowledge file is unavailable")
        return ""

SYSTEM += "\\n\\nAutorenspezifisches Forschungswissen (mit Evidenzstatus kennzeichnen):\\n" + load_author_research_context()

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
        "openai_configured": bool(ACTIVE_CLIENT and AI_ENABLED),
        "provider": ACTIVE_PROVIDER,
        "models": ([{"id": OPENAI_MODEL, "provider": "openai"}] if client else []) + ([{"id": OPENROUTER_MODEL, "provider": "openrouter"}] if router_client else []),
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
    if ACTIVE_CLIENT is None:
        return jsonify({"ok": False, "error": "Kein KI-Anbieter konfiguriert. Setze OPENAI_API_KEY oder OPENROUTER_API_KEY in Render."}), 503
    session_id, history = get_session(data.get("session_id"), data.get("history"))
    input_items = (history + [{"role": "user", "content": message}])[-MAX_HISTORY:]
    try:
        if ACTIVE_PROVIDER == "openrouter":
            messages = [{"role": "system", "content": SYSTEM}] + input_items
            response = ACTIVE_CLIENT.chat.completions.create(model=MODEL, messages=messages)
            answer = (response.choices[0].message.content or "").strip()
        else:
            kwargs = {"model": MODEL, "instructions": SYSTEM, "input": input_items, "store": False}
            if WEB_SEARCH:
                kwargs["tools"] = [{"type": "web_search", "search_context_size": "medium"}]
                kwargs["tool_choice"] = "auto"
            # The Responses API only accepts reasoning settings for reasoning-capable models.
            # The default gpt-4o-mini model does not support this parameter.
            reasoning_model = MODEL.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))
            if reasoning_model and REASONING_EFFORT in {"low", "medium", "high", "xhigh", "max"}:
                kwargs["reasoning"] = {"effort": REASONING_EFFORT}
            response = ACTIVE_CLIENT.responses.create(**kwargs)
            answer = (response.output_text or "").strip()
        if not answer:
            answer = "Ich konnte diesmal keine Textantwort erzeugen. Bitte versuche es erneut."
        final_history = (input_items + [{"role": "assistant", "content": answer}])[-MAX_HISTORY:]
        with sessions_lock:
            sessions[session_id] = final_history
        return jsonify({"ok": True, "response": answer, "answer": answer, "model": MODEL, "provider": ACTIVE_PROVIDER, "session_id": session_id})
    except Exception:
        app.logger.exception("Quantum.AI API error (%s / %s)", ACTIVE_PROVIDER, MODEL)
        return jsonify({"ok": False, "error": "Die KI-Schnittstelle ist fehlgeschlagen. Prüfe API-Key, Modellzugriff, Guthaben und Render-Logs."}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
