"""Function URL handler for the agenda parser. Runs outside the VPC, needs no database."""

import base64
import json
import logging
import os
import time
from datetime import date

import jwt
from jwt import PyJWKClient

from app.ai import agenda as ag

log = logging.getLogger()
log.setLevel(logging.INFO)

MAX_CHARS = 10_000
_jwks = None


class AuthError(Exception):
    pass


def verify_cognito_token(header: str) -> dict:
    """Checks a Cognito ID token (signature, issuer, audience). Raises AuthError."""
    global _jwks
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise AuthError("missing token")
    pool = os.environ["COGNITO_USER_POOL_ID"]
    issuer = f"https://cognito-idp.{pool.split('_')[0]}.amazonaws.com/{pool}"
    if _jwks is None:
        _jwks = PyJWKClient(f"{issuer}/.well-known/jwks.json")
    try:
        key = _jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=os.environ["COGNITO_CLIENT_ID"],
            issuer=issuer,
        )
    except jwt.PyJWTError as e:
        raise AuthError(str(e)) from e
    if claims.get("token_use") != "id":
        raise AuthError("not an id token")
    return claims


def _resp(status: int, body: dict) -> dict:
    # CORS headers come from the Function URL config, not from here
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context=None):
    try:
        user = verify_cognito_token(event.get("headers", {}).get("authorization", ""))
    except AuthError:
        return _resp(401, {"error": "unauthorized"})

    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw)
        text = body["text"]
        today = date.fromisoformat(body["today"])
        tz = str(body["tz"])
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty text")
    except (ValueError, KeyError, TypeError):
        return _resp(400, {"error": "send JSON with text, today (YYYY-MM-DD) and tz"})
    if len(text) > MAX_CHARS:  # before we pay for any tokens
        return _resp(413, {"error": f"text is longer than {MAX_CHARS} characters"})

    started = time.monotonic()
    try:
        parsed, usage = ag.parse_agenda(text, today, tz)
    except ag.AgendaParseError as e:
        return _resp(422, {"error": str(e)})
    except Exception as e:
        from anthropic import RateLimitError

        if isinstance(e, RateLimitError):
            return _resp(429, {"error": "the model is busy, try again in a minute"})
        log.exception("parse failed")
        return _resp(502, {"error": "the model call failed"})

    log.info(
        json.dumps(
            {
                "event": "agenda_parsed",
                "user": user["sub"],
                "model": ag.PARSER_MODEL,
                "prompt_version": ag.PROMPT_VERSION,
                **usage,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "cost_usd": ag.cost_usd(ag.PARSER_MODEL, usage),
            }
        )
    )
    return _resp(
        200,
        {
            "agenda": parsed.model_dump(mode="json"),
            "model": ag.PARSER_MODEL,
            "prompt_version": ag.PROMPT_VERSION,
        },
    )
