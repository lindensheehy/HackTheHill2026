"""Diagnose Auth0 settings from .env without a browser.

Run:  python -m api.auth_check [extra-origin ...]
      e.g. python -m api.auth_check https://triage.example.com

1. Checks the .env values are present and well-formed.
2. Fetches the tenant's OpenID configuration and JWKS (proves AUTH_DOMAIN is right).
3. For each app origin (http://localhost:8000 by default, plus DOMAIN and any arguments), sends the same
   /authorize request the SPA sends, without following redirects, and reports what Auth0 says:
   a login page (good), or an error such as a callback URL mismatch, an unknown client, or "Service not found"
   (a wrong AUTH_AUDIENCE). Nothing is created or changed in the tenant.
"""

import base64
import hashlib
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

from api.auth import config_problems
from engine import config


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _get(url, follow=True):
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "northwind-auth-check"}), timeout=15) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _origins(extra):
    out = ["http://localhost:8000"]
    if config.env("DOMAIN"):
        out.append(f"https://{config.env('DOMAIN').strip().rstrip('/')}")
    out += [o.rstrip("/") for o in extra]
    return list(dict.fromkeys(out))


def probe_authorize(origin):
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {"client_id": config.AUTH_CLIENT_ID, "redirect_uri": origin, "response_type": "code",
              "response_mode": "query", "scope": "openid profile email", "audience": config.AUTH_AUDIENCE,
              "state": secrets.token_urlsafe(8), "nonce": secrets.token_urlsafe(8),
              "code_challenge": challenge, "code_challenge_method": "S256"}
    status, headers, body = _get(f"https://{config.AUTH_DOMAIN}/authorize?" + urllib.parse.urlencode(params), follow=False)
    loc = headers.get("Location") or headers.get("location") or ""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(loc).query))
    if status in (301, 302, 303) and ("/u/login" in loc or "/login" in loc) and "error" not in q:
        return True, "OK: Auth0 shows its login page for this origin"
    if "error" in q:
        return False, f"{q.get('error')}: {q.get('error_description', '')}"
    text = body.decode(errors="ignore")
    for needle in ("Callback URL mismatch", "Unknown client", "Service not found", "invalid_request"):
        if needle.lower() in text.lower():
            return False, f"Auth0 error page mentions '{needle}' (HTTP {status})"
    return False, f"unexpected response: HTTP {status}, Location={loc[:120] or '-'}"


def main(extra=()):
    ok = True
    print("AUTH_ENABLED  :", config.AUTH_ENABLED)
    print("AUTH_DOMAIN   :", config.AUTH_DOMAIN or "(empty)")
    print("AUTH_CLIENT_ID:", (config.AUTH_CLIENT_ID[:6] + "…") if config.AUTH_CLIENT_ID else "(empty)")
    print("AUTH_AUDIENCE :", config.AUTH_AUDIENCE or "(empty)")
    probs = config_problems() if config.AUTH_ENABLED else ["AUTH_ENABLED is not true, so login is off"]
    for p in probs:
        print("  ✗", p)
    if probs:
        return False

    status, _, body = _get(f"https://{config.AUTH_DOMAIN}/.well-known/openid-configuration")
    if status != 200:
        print(f"  ✗ Can't read https://{config.AUTH_DOMAIN}/.well-known/openid-configuration (HTTP {status}). AUTH_DOMAIN is wrong.")
        return False
    issuer = json.loads(body).get("issuer")
    if issuer != f"https://{config.AUTH_DOMAIN}/":
        print(f"  ✗ Issuer is {issuer!r}, but the API expects 'https://{config.AUTH_DOMAIN}/'. Use the domain from the issuer.")
        ok = False
    else:
        print("  ✓ Tenant domain found; issuer matches")
    status, _, body = _get(f"https://{config.AUTH_DOMAIN}/.well-known/jwks.json")
    print("  ✓ Signing keys (JWKS) reachable" if status == 200 and b'"keys"' in body else f"  ✗ JWKS not reachable (HTTP {status})")

    print("\nLogin request per app origin (must be listed in the SPA's Allowed Callback URLs, exactly):")
    for origin in _origins(extra):
        good, msg = probe_authorize(origin)
        ok &= good
        print(f"  {'✓' if good else '✗'} {origin}: {msg}")
    print("\nNote: step 3 reads Auth0's responses, which Auth0 may change; treat a ✗ there as a strong hint, not proof.")
    return ok


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    sys.exit(0 if main(sys.argv[1:]) else 1)
