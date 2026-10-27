# Hippocrates Two-Site Demo

This project contains two separate website folders and one shared Flask API:

- `patient-website/` contains the public chatbot and appointment request form.
- `doctor-portal/` contains the clinician-facing appointment queue UI.
- `server.py` serves both pages and the API routes they use.

## Demo behavior

Regular chat messages are sent to Groq for a response but are not saved to the doctor queue. The patient must explicitly submit an appointment request and agree to share the entered details. Sharing chat context is a separate optional choice: the patient asks Groq to create a concise summary, reviews and may edit it, then submits that summary with the booking. The raw transcript is not attached to the booking. The summary is patient-reported context, not a diagnosis or a clinically verified record; it is limited to under 1,000 words.

This is a fictional-data demo, not a clinical system. The doctor portal and records API have no login and are publicly accessible. Records use temporary in-memory storage, are capped at 100, and are cleared when the server restarts or redeploys. Never use real patient names, contact details, health details, symptoms, diagnoses, or appointment information.

The demo scheduler offers weekday appointments every 30 minutes from 9:00 AM through 4:30 PM in the visitor's local timezone. A slot is reserved when a booking is accepted and duplicate bookings are rejected while this server process is running. Since reservations are memory-only, they reset on restart/redeploy and do not coordinate across multiple server instances; use a persistent shared database and transactional unique-slot constraint before using this for real scheduling.

After reserving a slot, the server attempts to send a confirmation using SMTP. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM`. Port 587 uses STARTTLS by default; set `SMTP_USE_SSL=true` for implicit TLS, commonly on port 465. If SMTP is not configured or delivery fails, the booking remains reserved and the response reports that email was not sent.

## Run locally

From this folder:

```sh
python3 -m pip install -r requirements.txt
cp .env.example .env
# Edit .env locally and set your private Groq and SMTP credentials.
python3 server.py
```

For Gmail SMTP, use `smtp.gmail.com`, port `587`, and `SMTP_USE_SSL=false`. Gmail requires an App Password; your regular account password will not work. If your Google account cannot use App Passwords, use SMTP credentials from another email provider. Replace the placeholders in your ignored local `.env` and never commit it.

Open the patient site at http://127.0.0.1:5004/ and the doctor portal at http://127.0.0.1:5004/doctor. Keep the terminal running. Use only fictional data.

## Deploy as one service

Upload the contents of this project folder to a GitHub repository. In Render, create a Blueprint from the repository; `render.yaml` defines the build command, start command, and SMTP environment variables. Add the SMTP values in Render's Environment settings. Never commit `.env` or SMTP credentials to GitHub.

The patient site and doctor portal have separate page URLs on the same app, but share one origin and one backend. The doctor URL is `/doctor` and is not protected in this demo. Do not deploy with real patient data. For real use, first select an approved hosting and data platform, then design authentication, authorization, durable storage, audit logs, consent and retention controls, and privacy/security review for the applicable jurisdiction.
