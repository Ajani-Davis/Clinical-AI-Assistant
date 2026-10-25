# Hippocrates Two-Site Demo

This project contains two separate website folders and one shared Flask API:

- `patient-website/` contains the public chatbot and appointment request form.
- `doctor-portal/` contains the clinician-facing appointment queue UI.
- `server.py` serves both pages and the API routes they use.

## Demo behavior

Regular chat messages are sent to Groq for a response but are not saved to the doctor queue. The patient must explicitly submit an appointment request and agree to share the entered details. Sharing chat context is a separate optional checkbox. Only submitted appointment requests enter the doctor's queue.

This is a fictional-data demo, not a clinical system. The doctor portal and records API have no login and are publicly accessible. Records use temporary in-memory storage, are capped at 100, and are cleared when the server restarts or redeploys. Never use real patient names, contact details, health details, symptoms, diagnoses, or appointment information.

## Run locally

From this folder:

```sh
python3 -m pip install -r requirements.txt
export GROQ_API_KEY="your-current-groq-key"
python3 server.py
```

Open the patient site at http://127.0.0.1:5004/ and the doctor portal at http://127.0.0.1:5004/doctor. Keep the terminal running. Use only fictional data.

## Deploy as one service

Upload the contents of this project folder to a GitHub repository. In Render, create a Python web service with:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn server:app`
- Environment variable: `GROQ_API_KEY` set in the Render dashboard, never in GitHub

The patient site and doctor portal have separate page URLs on the same app, but share one origin and one backend. The doctor URL is `/doctor` and is not protected in this demo. Do not deploy with real patient data. For real use, first select an approved hosting and data platform, then design authentication, authorization, durable storage, audit logs, consent and retention controls, and privacy/security review for the applicable jurisdiction.
