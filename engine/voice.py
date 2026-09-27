"""Spoken customer updates (optional ElevenLabs).

The words come from fixed templates filled with the live case state: no LLM writes them. The template never
invents repair dates and never says a case is resolved unless an agent resolved it. The only date is the
SLA target date, which is policy.

- With ELEVENLABS_API_KEY: audio from ElevenLabs (flash model), cached on disk by text hash (a replay costs
  nothing), capped per request and per day.
- Without it (FOSS mode): the browser's built-in speechSynthesis reads the same text.
"""

import hashlib
import json
import urllib.error
import urllib.request

import pandas as pd

from engine import config, usage

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format={fmt}"
CACHE_DIR = config.ROOT / "data" / "tts_cache"

NEXT_STEP = {
    "Bill corrected and re-issued": "we check your bill and, if it's wrong, correct it and send you a new one",
    "Refund or credit applied": "we check your account and apply any refund or credit that's due",
    "Information provided only": "we send you a clear explanation of what happened",
    "No action - explained to customer": "we explain how your bill was worked out",
    "Meter visit required": "we may need to visit to read or check your meter. We'll contact you to agree a time",
    "Payment plan amended": "we review your payment plan with you",
    "Appointment rebooked by agent": "we rebook your appointment and confirm it with you",
    "Compensation payment issued": "we check whether a compensation payment is due",
    "Apology and manual process fix": "we look into what went wrong and put it right",
    "Field repair required": "an engineer may need to carry out a repair. We'll contact you to arrange it",
}
TOPIC = {
    "Billing - disputed amount": "a disputed bill",
    "Billing - estimated read": "an estimated meter reading",
    "Metering - no read taken": "a missed meter reading",
    "Payment - plan or arrears": "your payment plan",
    "Service - missed appointment": "a missed appointment",
    "Service - poor communication": "how we've communicated with you",
    "Supply - interruption": "a supply interruption",
    "Water - pressure or quality": "water pressure or quality",
    "Other": "your enquiry",
}


def _nice_date(d):
    t = pd.Timestamp(d)
    return f"{t.day} {t.strftime('%B %Y')}"


def case_update_text(detail):
    """Customer-facing update for one case, from its current state."""
    c, s, t = detail["case"], detail["summary"], detail["triage"]
    ref = c["complaint_id"].replace("NW-", "N W ")
    topic = TOPIC.get(c["category"], "your complaint")
    action = (t["resolution_path"] or [{}])[0].get("action")
    step = NEXT_STEP.get(action, "we review your complaint")
    team = c["owner_team"]
    due = _nice_date(s["due_date"])
    status = c["workflow_status"]
    lines = [f"Hello. This is an update on your complaint, reference {ref}, about {topic}."]
    if c.get("in_auto_lane"):
        lines.append("We've sent you an answer to your question. If it doesn't solve things, just tell us "
                     "and a member of our team will pick it up straight away.")
    elif status == "resolved":
        lines.append("Our team has marked your complaint as resolved. If anything is still not right, "
                     "tell us and it will come straight back to us.")
    else:
        if status == "escalated":
            lines.append(f"It has been passed to a senior member of our {team} team.")
        elif status == "in_progress":
            lines.append(f"Our {team} team is working on it now.")
        else:
            lines.append(f"We've received it and it's with our {team} team.")
        lines.append(f"The most likely next step is that {step}.")
        if c["overdue_days"] > 0:
            lines.append("We're sorry this is taking longer than our target. It is now being prioritised.")
        else:
            lines.append(f"We aim to respond by {due}.")
    if detail.get("alert"):
        lines.append("We're also looking into a wider issue in your area that may be related.")
    lines.append("You can read this message on screen at any time.")
    return " ".join(lines)


def elevenlabs_enabled():
    return bool(config.ELEVENLABS_API_KEY)


def _cache_path(text):
    key = f"{config.ELEVENLABS_VOICE_ID}|{config.ELEVENLABS_MODEL}|{config.ELEVENLABS_OUTPUT_FORMAT}|{text}"
    return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest() + ".mp3")


def synthesize(text):
    """MP3 bytes for `text` via ElevenLabs. Cached; capped. Raises BudgetExceeded / RuntimeError."""
    if not elevenlabs_enabled():
        raise RuntimeError("ElevenLabs is not configured")
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("empty text")
    if len(text) > config.ELEVENLABS_MAX_CHARS_PER_REQUEST:
        raise ValueError(f"text longer than {config.ELEVENLABS_MAX_CHARS_PER_REQUEST} characters")
    path = _cache_path(text)
    if path.exists():
        return path.read_bytes(), True
    usage.check("elevenlabs", len(text))
    audio = request_tts(text)
    usage.add("elevenlabs", len(text))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio, False


HINTS = {
    "invalid_api_key": "ELEVENLABS_API_KEY is wrong or was deleted. Create a new key in ElevenLabs → Developers → API Keys.",
    "missing_permissions": "The API key is restricted. Edit it in ElevenLabs → Developers → API Keys and enable Text to Speech (and Voices: read).",
    "quota_exceeded": "The ElevenLabs account is out of credits. Redeem the Hack the Hill Creator code or check Subscription.",
    "voice_not_found": "ELEVENLABS_VOICE_ID isn't available to this account. Pick a voice in the Voice Library and copy its ID.",
    "detected_unusual_activity": "ElevenLabs blocked free-tier API use from this network (common on VPNs and cloud servers). Upgrade (e.g. the Creator code) or use another network.",
    "model_not_found": "ELEVENLABS_MODEL isn't a valid model ID. Use eleven_flash_v2_5.",
}


def request_tts(text):
    """One raw ElevenLabs call (no cache, no budget). Raises RuntimeError with a readable reason."""
    req = urllib.request.Request(
        TTS_URL.format(voice=config.ELEVENLABS_VOICE_ID, fmt=config.ELEVENLABS_OUTPUT_FORMAT),
        data=json.dumps({"text": text, "model_id": config.ELEVENLABS_MODEL}).encode(),
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(explain_error(e.code, e.read().decode(errors="ignore"))) from None
    except (urllib.error.URLError, OSError) as e:  # DNS, firewall, proxy, timeout
        raise RuntimeError(f"Can't reach api.elevenlabs.io ({getattr(e, 'reason', e)}). Check the internet connection or firewall.") from None


def explain_error(code, body):
    """Turn an ElevenLabs error response into one readable line (status + message + what to do)."""
    status, message = "", body[:200]
    try:
        detail = json.loads(body).get("detail")
        if isinstance(detail, dict):
            status, message = detail.get("status", "") or detail.get("code", ""), detail.get("message", message)
        elif isinstance(detail, str):
            message = detail
    except (ValueError, AttributeError):
        pass
    hint = HINTS.get(status) or ("The API key was rejected." if code == 401 else "")
    return f"ElevenLabs HTTP {code}{f' {status}' if status else ''}: {message}" + (f" → {hint}" if hint else "")


def status():
    return {"elevenlabs": elevenlabs_enabled(), "model": config.ELEVENLABS_MODEL if elevenlabs_enabled() else None,
            "max_chars_per_request": config.ELEVENLABS_MAX_CHARS_PER_REQUEST,
            "browser_fallback": config.VOICE_BROWSER_FALLBACK}
