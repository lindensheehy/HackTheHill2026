"""Optional authentication and permissions (standard OIDC bearer tokens; configured for Auth0).

Why: complaint records identify customers (account IDs, histories), so a hosted deployment must not be open.
Permissions are enforced here on every endpoint, not by hiding buttons.

- AUTH_ENABLED=false (default, FOSS mode): every request acts as a local admin.
- AUTH_ENABLED=true: RS256 access tokens are verified against https://{AUTH_DOMAIN}/.well-known/jwks.json with
  audience AUTH_AUDIENCE. Role resolution, first match wins:
    1. the token's `permissions` claim (Auth0 "Add Permissions in the Access Token"), if present;
    2. a roles claim (AUTH_ROLES_CLAIM, e.g. set by an Auth0 Action);
    3. AUTH_ROLE_MAP by email or sub ("alice@x.com:lead,auth0|123:analyst");
    4. AUTH_DEFAULT_ROLE (viewer).
  Nothing here needs Auth0's paid RBAC features, and any OIDC provider (e.g. Keycloak) works.
"""

from functools import lru_cache

from fastapi import Depends, HTTPException, Request

from engine import config

PERMISSIONS = ["read", "assistant:use", "cases:write", "intake:create", "cases:assign",
               "alerts:simulate", "signals:write", "demo:reset"]
ROLES = {
    "viewer": ["read", "assistant:use"],
    "agent": ["read", "assistant:use", "cases:write", "intake:create"],
    "lead": ["read", "assistant:use", "cases:write", "intake:create", "cases:assign"],
    "analyst": ["read", "assistant:use", "cases:write", "intake:create", "cases:assign",
                "alerts:simulate", "signals:write", "demo:reset"],
}
ROLE_ORDER = ["viewer", "agent", "lead", "analyst"]
LOCAL_USER = {"sub": "local", "name": "Local demo (auth off)", "role": "analyst", "permissions": PERMISSIONS, "auth": False}


def _role_map():
    out = {}
    for pair in filter(None, (p.strip() for p in config.AUTH_ROLE_MAP.split(","))):
        who, _, role = pair.rpartition(":")
        if who and role in ROLES:
            out[who.strip().lower()] = role
    return out


@lru_cache(maxsize=1)
def _jwks_client():
    import jwt
    return jwt.PyJWKClient(f"https://{config.AUTH_DOMAIN}/.well-known/jwks.json", cache_keys=True)


def signing_key(token):
    """Separated so tests can inject a local key."""
    return _jwks_client().get_signing_key_from_jwt(token).key


def verify(token):
    import jwt
    try:
        return jwt.decode(token, signing_key(token), algorithms=["RS256"], audience=config.AUTH_AUDIENCE,
                          issuer=f"https://{config.AUTH_DOMAIN}/")
    except Exception as e:
        raise HTTPException(401, f"invalid token: {e}") from None


def resolve(claims):
    ns = config.AUTH_ROLES_CLAIM.rsplit("/", 1)[0]
    email = (claims.get("email") or claims.get(f"{ns}/email") or "").lower()
    name = claims.get("name") or claims.get(f"{ns}/name") or email or claims.get("sub")
    perms = [p for p in claims.get("permissions") or [] if p in PERMISSIONS]
    if perms:
        role = next((r for r in reversed(ROLE_ORDER) if set(ROLES[r]) <= set(perms) | {"read", "assistant:use"}), "viewer")
        return {"sub": claims.get("sub"), "name": name, "role": role,
                "permissions": sorted(set(perms) | {"read", "assistant:use"}, key=PERMISSIONS.index), "auth": True}
    roles = [r for r in claims.get(config.AUTH_ROLES_CLAIM) or [] if r in ROLES]
    mapped = _role_map()
    role = (max(roles, key=ROLE_ORDER.index) if roles
            else mapped.get(email) or mapped.get(str(claims.get("sub", "")).lower()) or config.AUTH_DEFAULT_ROLE)
    role = role if role in ROLES else "viewer"
    return {"sub": claims.get("sub"), "name": name, "role": role, "permissions": ROLES[role], "auth": True}


def current_user(request: Request):
    if not config.AUTH_ENABLED:
        return LOCAL_USER
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "login required")
    return resolve(verify(header[7:].strip()))


def require(permission):
    def dep(user=Depends(current_user)):
        if permission not in user["permissions"]:
            raise HTTPException(403, f"your role ({user['role']}) can't do this: needs '{permission}'")
        return user
    return dep


def config_problems():
    """Settings that would make login fail. Empty list = looks sane (it can't prove the values match Auth0)."""
    if not config.AUTH_ENABLED:
        return []
    probs = []
    if not config.AUTH_DOMAIN:
        probs.append("AUTH_DOMAIN is empty (expected like your-tenant.us.auth0.com)")
    elif "/" in config.AUTH_DOMAIN or "." not in config.AUTH_DOMAIN:
        probs.append(f"AUTH_DOMAIN looks wrong: {config.AUTH_DOMAIN!r} (expected a bare host like your-tenant.us.auth0.com)")
    if not config.AUTH_CLIENT_ID:
        probs.append("AUTH_CLIENT_ID is empty (the Client ID of the Single Page Application)")
    if not config.AUTH_AUDIENCE:
        probs.append("AUTH_AUDIENCE is empty (the Identifier of the Auth0 API). Without it Auth0 issues tokens the API can't verify")
    return probs


def public_config():
    return {"enabled": config.AUTH_ENABLED, "domain": config.AUTH_DOMAIN if config.AUTH_ENABLED else None,
            "client_id": config.AUTH_CLIENT_ID if config.AUTH_ENABLED else None,
            "audience": config.AUTH_AUDIENCE if config.AUTH_ENABLED else None}
