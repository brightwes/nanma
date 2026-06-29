"""
Nanma — Voice-to-SMS helper for elderly users.

Flow:
  1. User calls the Twilio number.
  2. Twilio greets them and records their spoken question.
  3. On recording completion, the webhook fires here.
  4. We transcribe via OpenAI Whisper, generate a response via GPT,
     then send two SMS messages back to the caller:
       • Message 1 — context / instructions for the caller
       • Message 2 — the clean, copy-pasteable answer
"""

import os
import httpx

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Form
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse
from openai import OpenAI

load_dotenv()

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
twilio = TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
TWILIO_NUMBER = os.environ["TWILIO_PHONE_NUMBER"]   # e.g. "+15005550006"

app = FastAPI()

# ---------------------------------------------------------------------------
# TwiML helpers
# ---------------------------------------------------------------------------

TWIML_CONTENT_TYPE = "text/xml"


def twiml_response(twiml: VoiceResponse) -> Response:
    return Response(content=str(twiml), media_type=TWIML_CONTENT_TYPE)


# ---------------------------------------------------------------------------
# Inbound call — greet and record
# ---------------------------------------------------------------------------

@app.post("/voice")
async def inbound_call():
    """
    Twilio calls this when someone dials the Nanma number.
    We greet them and start recording.
    """
    vr = VoiceResponse()
    vr.say(
        "Hello! This is Nanma. After the beep, please say your question or "
        "what you need help writing. When you're done, press the pound key or "
        "just stop talking for a few seconds.",
        voice="Polly.Joanna",
    )
    vr.record(
        action="/recording-complete",
        method="POST",
        max_length=120,           # 2 minutes max
        finish_on_key="#",
        transcribe=False,         # we use Whisper instead
        play_beep=True,
    )
    vr.say("We didn't receive a recording. Please call back and try again.", voice="Polly.Joanna")
    return twiml_response(vr)


# ---------------------------------------------------------------------------
# Recording complete — transcribe → GPT → SMS
# ---------------------------------------------------------------------------

@app.post("/recording-complete")
async def recording_complete(
    background_tasks: BackgroundTasks,
    RecordingUrl: str = Form(...),
    CallSid: str = Form(...),
    From: str = Form(...),
):
    """
    Twilio posts here when the recording is ready.
    We acknowledge immediately (Twilio has a 15s webhook timeout) and do the
    heavy work — download, Whisper, GPT, SMS — in a background task.
    Vercel Fluid Compute keeps the function alive until background tasks finish.
    """
    background_tasks.add_task(_process_recording, RecordingUrl, From)
    return Response(content="<Response/>", media_type=TWIML_CONTENT_TYPE)


async def _process_recording(recording_url: str, caller_number: str) -> None:
    """Download the recording, transcribe, generate a response, and SMS the caller."""
    # 1. Download the recording (Twilio requires auth for .mp3 access)
    audio_url = recording_url + ".mp3"
    async with httpx.AsyncClient() as client:
        audio_resp = await client.get(
            audio_url,
            auth=(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]),
            timeout=30,
        )
    audio_bytes = audio_resp.content

    # 2. Transcribe with Whisper
    transcription = openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=("recording.mp3", audio_bytes, "audio/mpeg"),
    )
    question = transcription.text.strip()

    if not question:
        _send_sms(
            caller_number,
            "Hi! We received your call but couldn't make out what you said. "
            "Please try calling again and speak clearly after the beep.",
        )
        return

    # 3. Generate response via GPT
    meta_msg, answer_msg = await _generate_response(question)

    # 4. Send two SMS messages
    _send_sms(caller_number, meta_msg)
    _send_sms(caller_number, answer_msg)


# ---------------------------------------------------------------------------
# GPT response generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are Nanma, a warm and patient assistant helping elderly people communicate.
The user has called and spoken a question or described something they want help writing or communicating.

You must reply in exactly two parts, separated by the delimiter: ---ANSWER---

Part 1 (before ---ANSWER---):
Write a brief, friendly message TO the caller — acknowledge what they asked,
let them know the answer is in the next text message, and offer any simple instructions
(e.g. "You can copy and paste the message below and send it to your doctor.").
Keep it to 2–3 short sentences. Use plain, warm language — no jargon.

Part 2 (after ---ANSWER---):
Write ONLY the actual response or message the person needs — the thing they can forward,
copy-paste, or read aloud. No extra commentary. No greeting to the caller.
Just the clean, finished message or answer.
""".strip()


async def _generate_response(question: str) -> tuple[str, str]:
    completion = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        max_tokens=600,
        temperature=0.4,
    )
    raw = completion.choices[0].message.content or ""

    if "---ANSWER---" in raw:
        meta, answer = raw.split("---ANSWER---", 1)
    else:
        # Fallback: treat the whole thing as the answer
        meta = "Hi! Here is the response to your question:"
        answer = raw

    return meta.strip(), answer.strip()


# ---------------------------------------------------------------------------
# SMS helper
# ---------------------------------------------------------------------------

def _send_sms(to: str, body: str) -> None:
    twilio.messages.create(
        to=to,
        from_=TWILIO_NUMBER,
        body=body,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/")
async def health():
    return {"status": "ok", "service": "Nanma"}
