"""Verify an interactive Auth0 user token without printing or storing the token."""

import asyncio
import base64
import hashlib
import html
import secrets
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from business_brain.core.config import Settings
from business_brain.security.auth0 import Auth0TokenValidator, TokenValidationError

CALLBACK_URL = "http://127.0.0.1:8765/callback"


class CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return
        values = {key: items[0] for key, items in parse_qs(parsed.query).items() if items}
        type(self).result = values
        error = values.get("error")
        if error:
            message = f"Auth0 login failed: {html.escape(error)}. You may close this tab."
            status = 400
        else:
            message = "Auth0 login received. Return to Codex; you may close this tab."
            status = 200
        body = f"<!doctype html><title>Business Brain Auth0</title><p>{message}</p>".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def build_authorize_url(settings: Settings, state: str, verifier: str) -> str:
    if not settings.auth0_domain or not settings.auth0_audience or not settings.auth0_client_id:
        raise RuntimeError("AUTH0_DOMAIN, AUTH0_AUDIENCE, and AUTH0_CLIENT_ID are required")
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.auth0_client_id,
            "redirect_uri": CALLBACK_URL,
            "audience": settings.auth0_audience,
            "scope": "openid profile email",
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "state": state,
            "prompt": "login",
        }
    )
    return f"https://{settings.auth0_domain.rstrip('/')}/authorize?{query}"


def await_callback(timeout_seconds: int = 600) -> dict[str, str]:
    CallbackHandler.result = None
    with HTTPServer(("127.0.0.1", 8765), CallbackHandler) as server:
        server.timeout = 1
        deadline = monotonic() + timeout_seconds
        while CallbackHandler.result is None and monotonic() < deadline:
            server.handle_request()
    if CallbackHandler.result is None:
        raise TimeoutError("Timed out waiting for Auth0 login")
    return CallbackHandler.result


async def exchange_and_validate(
    settings: Settings,
    *,
    code: str,
    verifier: str,
) -> None:
    token_url = f"https://{settings.auth0_domain.rstrip('/')}/oauth/token"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.auth0_client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": CALLBACK_URL,
            },
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
    if not isinstance(access_token, str):
        raise RuntimeError("Auth0 did not return an access token")

    validator = Auth0TokenValidator(
        domain=settings.auth0_domain or "",
        audience=settings.auth0_audience or "",
        tenant_claim=settings.auth0_tenant_claim,
        role_claim=settings.auth0_role_claim,
        cache_seconds=settings.auth0_jwks_cache_seconds,
        clock_skew_seconds=settings.auth0_clock_skew_seconds,
    )
    identity = await validator.validate(access_token)
    print("Auth0 live verification passed.")
    print(f"tenant_id={identity.tenant_id}")
    print(f"user_id={identity.user_id}")
    print(f"role={identity.role.value}")
    print("Access token was not printed or stored.")


def main() -> int:
    settings = Settings()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    try:
        authorize_url = build_authorize_url(settings, state, verifier)
        print("Open this URL in a browser and sign in with the Auth0 test user:")
        print(authorize_url)
        sys.stdout.flush()
        callback = await_callback()
        if callback.get("state") != state:
            raise RuntimeError("Auth0 callback state did not match")
        if "error" in callback:
            raise RuntimeError(f"Auth0 returned error: {callback['error']}")
        code = callback.get("code")
        if not code:
            raise RuntimeError("Auth0 callback did not contain an authorization code")
        asyncio.run(exchange_and_validate(settings, code=code, verifier=verifier))
    except (httpx.HTTPError, RuntimeError, TimeoutError, TokenValidationError) as exc:
        print(f"Auth0 verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
