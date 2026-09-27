"""Diagnose the ElevenLabs settings from .env without the browser.

Run:  python -m engine.voice_check [--save out.mp3]

Checks the key is set, that the voice exists for this account, and makes one real ~20-character text-to-speech
call (bypassing the app's cache and daily cap, so it always tests the live key; it costs about 10-20 credits).
"""

import json
import sys
import urllib.error
import urllib.request

from engine import config, voice

TEST_TEXT = "Northwind voice check."


def _get(path):
    req = urllib.request.Request(f"https://api.elevenlabs.io{path}", headers={"xi-api-key": config.ELEVENLABS_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")
    except (urllib.error.URLError, OSError) as e:
        return 0, str(getattr(e, "reason", e))


def main(save=None):
    key = config.ELEVENLABS_API_KEY
    print("ELEVENLABS_API_KEY :", f"{key[:6]}… ({len(key)} chars)" if key else "(empty)")
    print("ELEVENLABS_VOICE_ID:", config.ELEVENLABS_VOICE_ID)
    print("ELEVENLABS_MODEL   :", config.ELEVENLABS_MODEL)
    print("Browser fallback   :", "on" if config.VOICE_BROWSER_FALLBACK else "off")
    if not key:
        print("  ✗ No key: the app will use the browser's voice. Add ELEVENLABS_API_KEY to .env and restart the server.")
        return False
    if not key.startswith("sk_"):
        print("  ! ElevenLabs keys normally start with 'sk_'. Check you copied the whole key (not the key's name or ID).")

    code, body = _get(f"/v1/voices/{config.ELEVENLABS_VOICE_ID}")
    if code == 200:
        print(f"  ✓ Voice found: {body.get('name')}")
    elif code == 0:
        print(f"  ✗ Can't reach api.elevenlabs.io: {body}")
        return False
    else:
        # A key restricted to Text to Speech can't read voices; the TTS call below is the real test.
        print(f"  ! Voice lookup: {voice.explain_error(code, body)}")

    code, body = _get("/v1/user/subscription")
    if code == 200:
        left = body.get("character_limit", 0) - body.get("character_count", 0)
        print(f"  ✓ Plan: {body.get('tier')} · about {left:,} credits left this period")
    else:
        print("  · Couldn't read the subscription (the key may lack User: read permission; not needed by the app)")

    try:
        audio = voice.request_tts(TEST_TEXT)
    except RuntimeError as e:
        print(f"  ✗ Text to speech failed: {e}")
        return False
    print(f"  ✓ Text to speech works: {len(audio):,} bytes of audio")
    if save:
        open(save, "wb").write(audio)
        print(f"    saved to {save}")
    print("\nIf the app still uses the Windows voice: restart the server (it reads .env only at start-up), then reload the page.")
    return True


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    out = args[args.index("--save") + 1] if "--save" in args else None
    sys.exit(0 if main(out) else 1)
