import os
import json
from collections import deque
from datetime import date, datetime, time, timedelta, timezone
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from groq import Groq

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

PATIENT_DIR = os.path.join(ROOT_DIR, "patient-website")
DOCTOR_DIR = os.path.join(ROOT_DIR, "doctor-portal")
app = Flask(__name__)

# Fictional test requests only. This queue is deliberately temporary and bounded.
appointment_requests = deque(maxlen=100)
requests_lock = Lock()
reserved_slots = set()
SLOT_INTERVAL_MINUTES = 30
FIRST_SLOT_HOUR = 9
LAST_SLOT_HOUR = 16

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


def slots_for_date(selected_date, timezone_offset):
    if selected_date.weekday() >= 5:
        return []

    slot_time = time(FIRST_SLOT_HOUR, 0)
    last_slot = time(LAST_SLOT_HOUR, 30)
    slots = []
    while slot_time <= last_slot:
        slot_value = f"{selected_date.isoformat()}T{slot_time.strftime('%H:%M')}"
        local_now = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=timezone_offset)
        utc_key = slot_utc_key(selected_date, slot_time, timezone_offset)
        if datetime.combine(selected_date, slot_time) > local_now and utc_key not in reserved_slots:
            slots.append(slot_time.strftime("%H:%M"))
        slot_datetime = datetime.combine(selected_date, slot_time) + timedelta(minutes=SLOT_INTERVAL_MINUTES)
        slot_time = slot_datetime.time()
    return slots


def slot_utc_key(local_date, local_time, timezone_offset):
    utc_datetime = datetime.combine(local_date, local_time) + timedelta(minutes=timezone_offset)
    return utc_datetime.strftime("%Y-%m-%dT%H:%MZ")


def send_appointment_confirmation(record):
    api_key = os.environ.get("RESEND_API_KEY")
    sender = os.environ.get("RESEND_FROM")
    if not all((api_key, sender)):
        app.logger.warning("Resend is not configured; appointment confirmation email was not sent")
        return False

    appointment = datetime.strptime(record["requestedTime"], "%Y-%m-%dT%H:%M")
    body = (
        f"Hello {record['name']},\n\n"
        "Your appointment has been confirmed for "
        f"{appointment.strftime('%A, %B %-d, %Y at %-I:%M %p')} "
        "in the local timezone used when you selected the time.\n\n"
        "This is an automated confirmation. Please contact the clinic if you need to change your appointment.\n"
    )
    payload = json.dumps({
        "from": sender,
        "to": [record["email"]],
        "subject": "Your Hippocrates appointment confirmation",
        "text": body,
    }).encode("utf-8")
    api_request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(api_request, timeout=15) as response:
            if not 200 <= response.status < 300:
                app.logger.error("Resend returned HTTP %s for appointment confirmation", response.status)
                return False
        return True
    except HTTPError as error:
        app.logger.error("Resend returned HTTP %s for appointment confirmation", error.code)
        return False
    except (URLError, TimeoutError, OSError):
        app.logger.exception("Appointment booked, but Resend email delivery failed")
        return False


@app.get("/api/availability")
def appointment_availability():
    date_value = request.args.get("date", "")
    try:
        selected_date = date.fromisoformat(date_value)
        timezone_offset = int(request.args.get("timezoneOffset", "0"))
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a valid appointment date."}), 400
    if not -840 <= timezone_offset <= 840:
        return jsonify({"error": "Invalid timezone offset."}), 400

    with requests_lock:
        slots = slots_for_date(selected_date, timezone_offset)
    return jsonify({"date": date_value, "slots": slots})


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
                        "well under 500 words, preferably under 250 words. Return only the summary."
                    ),
                },
                {"role": "user", "content": transcript.strip()},
            ],
        )
        summary = (result.choices[0].message.content or "").strip()
        if not summary:
            return jsonify({"error": "The AI did not return a summary. Please try again."}), 502
        if len(summary.split()) >= 500:
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
    timezone_offset = data.get("timezoneOffset", 0)
    summary = data.get("summary", "")

    if data.get("demoOnly") is not True:
        return jsonify({"error": "Confirm this is fictional test data."}), 400
    if data.get("shareConsent") is not True:
        return jsonify({"error": "Consent is required to share the appointment request."}), 400
    if not all(isinstance(value, str) and value.strip() for value in (name, contact_number, email, requested_time)):
        return jsonify({"error": "Name, contact number, email, and a preferred appointment time are required."}), 400
    if len(name) > 100 or len(contact_number) > 40 or len(email) > 200 or len(requested_time) > 120 or not isinstance(summary, str) or len(summary) > 2000:
        return jsonify({"error": "One or more fields exceed the demo limits."}), 400
    if not isinstance(timezone_offset, int) or not -840 <= timezone_offset <= 840:
        return jsonify({"error": "Invalid appointment timezone."}), 400
    if summary and data.get("shareSummary") is not True:
        return jsonify({"error": "Choose whether to include the optional chat summary."}), 400
    if summary and len(summary.split()) >= 1000:
        return jsonify({"error": "The shared summary must be less than 1,000 words."}), 400

    try:
        appointment_datetime = datetime.strptime(requested_time, "%Y-%m-%dT%H:%M")
    except ValueError:
        return jsonify({"error": "Choose an available appointment date and time."}), 400
    if appointment_datetime.minute not in (0, 30) or appointment_datetime.second != 0:
        return jsonify({"error": "Choose one of the listed half-hour appointment slots."}), 400
    appointment_key = appointment_datetime.strftime("%Y-%m-%dT%H:%M")
    reservation_key = slot_utc_key(appointment_datetime.date(), appointment_datetime.time(), timezone_offset)

    record = {
        "id": str(uuid4()),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "name": name.strip(),
        "contactNumber": contact_number.strip(),
        "email": email.strip(),
        "requestedTime": appointment_key,
        "timezoneOffset": timezone_offset,
        "summary": summary.strip(),
        "status": "New",
    }
    with requests_lock:
        available_slots = slots_for_date(appointment_datetime.date(), timezone_offset)
        if appointment_datetime.strftime("%H:%M") not in available_slots:
            return jsonify({"error": "That appointment slot is no longer available. Choose another time."}), 409
        reserved_slots.add(reservation_key)
        appointment_requests.appendleft(record)
    email_sent = send_appointment_confirmation(record)
    if email_sent:
        message = "Appointment confirmed. A confirmation email was sent."
    else:
        message = "Appointment confirmed, but the confirmation email could not be sent. Contact the clinic to verify the booking."
    return jsonify({"message": message, "requestId": record["id"], "confirmationEmailSent": email_sent}), 201


@app.get("/api/appointments")
def list_appointment_requests():
    with requests_lock:
        records = list(appointment_requests)
    return jsonify({"requests": records})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5004"))
    app.run(host="0.0.0.0", port=port, debug=False)
