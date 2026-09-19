import os
from flask import Flask,jsonify,request,send_from_directory
from openai import OpenAI
app=Flask(__name__)
MODEL=os.getenv("OPENAI_MODEL","gpt-6-astra");WEB=os.getenv("ENABLE_WEB_SEARCH","true").lower()=="true"
client=OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
SYSTEM="""Du bist Quantum.AI, eine eigenständige Spitzen-KI. Arbeite gründlich und strukturiert,
prüfe Annahmen und Unsicherheit und liefere konkrete Ergebnisse. Nutze Websuche für aktuelle Fakten.
Behaupte keine nicht ausgeführten Aktionen. Antworte in der Sprache des Nutzers."""
@app.get("/")
def home(): return send_from_directory("frontend","index.html")
@app.get("/health")
@app.get("/api/health")
def health(): return jsonify({"status":"ok","project":"Quantum.AI.","model":MODEL,"web_search":WEB,"openai_configured":bool(client)})
@app.post("/chat")
@app.post("/api/chat")
def chat():
 d=request.get_json(silent=True) or {};m=str(d.get("message") or "").strip()
 if not m:return jsonify({"error":"message is required"}),400
 if not client:return jsonify({"error":"OPENAI_API_KEY ist nicht gesetzt."}),503
 try:
  tools=[{"type":"web_search","search_context_size":"medium"}] if WEB else []
  h=d.get("history") if isinstance(d.get("history"),list) else []
  r=client.responses.create(model=MODEL,reasoning={"effort":"high"},tools=tools,tool_choice="auto",store=False,input=[{"role":"system","content":SYSTEM},*h[-12:],{"role":"user","content":m}])
  return jsonify({"response":r.output_text or "Keine Antwort.","model":MODEL})
 except Exception:
  app.logger.exception("Quantum.AI API error");return jsonify({"error":"KI-Schnittstelle momentan nicht erreichbar."}),502
