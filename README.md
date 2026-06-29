# Nanma

A voice-to-SMS helper for people who aren't comfortable with technology.

**How it works:**
1. The user calls a phone number (powered by Twilio).
2. They speak their question or describe something they need help writing.
3. Nanma transcribes the recording with OpenAI Whisper, generates a response with GPT-4o, and sends **two text messages** back to the caller's number:
   - **Text 1** — a warm, plain-language note acknowledging their question and what to do next.
   - **Text 2** — the clean, ready-to-copy-paste answer or message, by itself.

---

## Stack

| Layer | Tool |
|---|---|
| Voice / SMS | [Twilio](https://twilio.com) |
| Transcription | OpenAI Whisper |
| Response generation | OpenAI GPT-4o |
| Server | FastAPI + uvicorn |

---

## Local setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/wesbright/nanma.git
cd nanma
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Fill in your Twilio and OpenAI credentials
```

### 3. Run the server

```bash
uvicorn app:app --reload
```

### 4. Expose locally with ngrok (for Twilio webhooks during development)

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok.io` URL and set these in your [Twilio phone number settings](https://console.twilio.com/us1/develop/phone-numbers/manage/active):

| Field | Value |
|---|---|
| **A call comes in** (Webhook) | `https://xxxx.ngrok.io/voice` |
| HTTP method | `POST` |

---

## Deploying to production

Any platform that can run a Python web process works. Railway and Render are the easiest:

### Railway
```bash
railway login
railway init
railway up
```
Set the environment variables in the Railway dashboard, then point your Twilio webhook at the Railway URL.

### Render / Heroku
The `Procfile` is already configured — connect the repo and set env vars in the dashboard.

---

## Environment variables

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | From the Twilio Console |
| `TWILIO_AUTH_TOKEN` | From the Twilio Console |
| `TWILIO_PHONE_NUMBER` | The Twilio number callers will dial (e.g. `+15005550006`) |
| `OPENAI_API_KEY` | From [platform.openai.com](https://platform.openai.com/api-keys) |
