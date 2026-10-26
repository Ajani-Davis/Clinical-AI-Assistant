import os
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory
from groq import Groq

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PATIENT_DIR = os.path.join(ROOT_DIR, "patient-website")
DOCTOR_DIR = os.path.join(ROOT_DIR, "doctor-portal")
app = Flask(__name__)

# Fictional test requests only. This queue is deliberately temporary and bounded.
appointment_requests = deque(maxlen=100)
requests_lock = Lock()

SYSTEM_PROMPT = (
    "You are Hippocrates, a helpful assistant for hospitals, health centers, "
    "and clinics. Give general information only. Do not diagnose or claim to "
    "schedule appointments. Encourage urgent cases to contact local emergency "
    "services or a healthcare professional immediately. Remind users this is a "
    "fictional-data demo and not to enter real personal or health information."
)


@app.get("/")
def patient_site():
    return send_from_directory(PATIENT_DIR, "Chatbot.html")


@app.get("/doctor")
def doctor_site():
    return send_from_directory(DOCTOR_DIR, "Doctor.html")


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Enter a message."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Keep demo messages under 2,000 characters."}), 400
    if data.get("demoOnly") is not True:
        return jsonify({"error": "Confirm this is fictional test data."}), 400

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return jsonify({"error": "Chat service is not configured. Set GROQ_API_KEY on the server."}), 503

    try:
        client = Groq(api_key=api_key)
        result = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.strip()},
            ],
        )
        reply = result.choices[0].message.content or "I don't have a response right now."
        return jsonify({"reply": reply})
    except Exception:
        app.logger.exception("Groq chat request failed")
        return jsonify({"error": "The chatbot could not complete that request."}), 502


@app.post("/api/summarize")
def summarize_chat():
    data = request.get_json(silent=True) or {}
    transcript = data.get("transcript")

    if data.get("demoOnly") is not True:
        return jsonify({"error": "Confirm this is fictional test data."}), 400
    if not isinstance(transcript, str) or not transcript.strip():
        return jsonify({"error": "There is no chat content to summarize."}), 400
    if len(transcript) > 12000:
        return jsonify({"error": "The chat excerpt is too long to summarize."}), 400

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return jsonify({"error": "Chat service is not configured. Set GROQ_API_KEY on the server."}), 503

    try:
        client = Groq(api_key=api_key)
        result = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize the provided fictional patient-chat transcript for a clinician to review. "
                        "Use only details the patient explicitly stated. Clearly distinguish patient-reported "
                        "information from assistant responses. Do not infer facts, make or suggest a diagnosis, "
                        "recommend treatment, or present the summary as clinically verified. Keep the summary "
                        "well under 1,000 words, preferably under 250 words. Return only the summary."
                    ),
                },
                {"role": "user", "content": transcript.strip()},
            ],
        )
        summary = (result.choices[0].message.content or "").strip()
        if not summary:
            return jsonify({"error": "The AI did not return a summary. Please try again."}), 502
        if len(summary.split()) >= 1000:
            return jsonify({"error": "The generated summary was too long. Please try again."}), 502
        return jsonify({"summary": summary, "wordCount": len(summary.split())})
    except Exception:
        app.logger.exception("Groq summary request failed")
        return jsonify({"error": "The chat could not be summarized. Please try again."}), 502


@app.post("/api/appointments")
def create_appointment_request():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    contact_number = data.get("contactNumber")
    email = data.get("email")
    requested_time = data.get("requestedTime")
    summary = data.get("summary", "")

    if data.get("demoOnly") is not True:
        return jsonify({"error": "Confirm this is fictional test data."}), 400
    if data.get("shareConsent") is not True:
        return jsonify({"error": "Consent is required to share the appointment request."}), 400
    if not all(isinstance(value, str) and value.strip() for value in (name, contact_number, email, requested_time)):
        return jsonify({"error": "Name, contact number, email, and a preferred appointment time are required."}), 400
    if len(name) > 100 or len(contact_number) > 40 or len(email) > 200 or len(requested_time) > 120 or not isinstance(summary, str) or len(summary) > 2000:
        return jsonify({"error": "One or more fields exceed the demo limits."}), 400
    if summary and data.get("shareSummary") is not True:
        return jsonify({"error": "Choose whether to include the optional chat summary."}), 400
    if summary and len(summary.split()) >= 1000:
        return jsonify({"error": "The shared summary must be less than 1,000 words."}), 400

    record = {
        "id": str(uuid4()),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "name": name.strip(),
        "contactNumber": contact_number.strip(),
        "email": email.strip(),
        "requestedTime": requested_time.strip(),
        "summary": summary.strip(),
        "status": "New",
    }
    with requests_lock:
        appointment_requests.appendleft(record)
    return jsonify({"message": "Fictional demo request submitted.", "requestId": record["id"]}), 201


@app.get("/api/appointments")
def list_appointment_requests():
    with requests_lock:
        records = list(appointment_requests)
    return jsonify({"requests": records})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5004"))
    app.run(host="0.0.0.0", port=port, debug=False)
