import asyncio
import re
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

import httpx
import jwt
from jwt import PyJWK

from business_brain.security.context import AuthContext, UserRole

JWKSFetcher = Callable[[str], Awaitable[dict[str, Any]]]
TENANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


class TokenValidationError(ValueError):
    """Token could not be safely mapped to an application identity."""


async def fetch_jwks(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise TokenValidationError("The identity provider returned invalid key data")
    return payload


class Auth0TokenValidator:
    def __init__(
        self,
        *,
        domain: str,
        audience: str,
        tenant_claim: str,
        role_claim: str,
        cache_seconds: int = 3600,
        clock_skew_seconds: int = 30,
        jwks_fetcher: JWKSFetcher = fetch_jwks,
    ) -> None:
        normalized_domain = domain.removeprefix("https://").rstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", normalized_domain):
            raise ValueError("AUTH0_DOMAIN must be an Auth0 hostname")
        self.issuer = f"https://{normalized_domain}/"
        self.jwks_url = f"{self.issuer}.well-known/jwks.json"
        self.audience = audience
        self.tenant_claim = tenant_claim
        self.role_claim = role_claim
        self.cache_seconds = cache_seconds
        self.clock_skew_seconds = clock_skew_seconds
        self._fetch_jwks = jwks_fetcher
        self._keys: dict[str, Any] = {}
        self._cache_expires_at = 0.0
        self._lock = asyncio.Lock()

    async def validate(self, token: str) -> AuthContext:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenValidationError("Bearer token is malformed") from exc
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise TokenValidationError("Bearer token uses an unsupported signing method")

        key = await self._get_key(header["kid"])
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.clock_skew_seconds,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenValidationError("Bearer token validation failed") from exc
        return self._identity_from_claims(claims)

    async def _get_key(self, kid: str) -> Any:
        if monotonic() >= self._cache_expires_at or kid not in self._keys:
            await self._refresh_keys()
        key = self._keys.get(kid)
        if key is None:
            raise TokenValidationError("Bearer token signing key is unknown")
        return key

    async def _refresh_keys(self) -> None:
        async with self._lock:
            try:
                payload = await self._fetch_jwks(self.jwks_url)
            except (httpx.HTTPError, TypeError, ValueError) as exc:
                raise TokenValidationError("Identity provider keys are unavailable") from exc
            raw_keys = payload.get("keys")
            if not isinstance(raw_keys, list):
                raise TokenValidationError("The identity provider returned invalid key data")
            keys: dict[str, Any] = {}
            try:
                for raw_key in raw_keys:
                    if isinstance(raw_key, dict) and isinstance(raw_key.get("kid"), str):
                        keys[raw_key["kid"]] = PyJWK.from_dict(raw_key).key
            except (jwt.PyJWTError, ValueError) as exc:
                raise TokenValidationError(
                    "The identity provider returned invalid key data"
                ) from exc
            if not keys:
                raise TokenValidationError("The identity provider returned no usable keys")
            self._keys = keys
            self._cache_expires_at = monotonic() + self.cache_seconds

    def _identity_from_claims(self, claims: dict[str, Any]) -> AuthContext:
        user_id = claims.get("sub")
        tenant_id = claims.get(self.tenant_claim)
        raw_role = claims.get(self.role_claim)
        if isinstance(raw_role, list):
            if len(raw_role) != 1:
                raise TokenValidationError("Bearer token must contain exactly one role")
            raw_role = raw_role[0]
        if not isinstance(user_id, str) or not user_id:
            raise TokenValidationError("Bearer token is missing the subject claim")
        if not isinstance(tenant_id, str) or not TENANT_PATTERN.fullmatch(tenant_id):
            raise TokenValidationError("Bearer token has an invalid tenant claim")
        try:
            role = UserRole(raw_role)
        except (TypeError, ValueError) as exc:
            raise TokenValidationError("Bearer token has an invalid role claim") from exc
        return AuthContext(tenant_id=tenant_id, user_id=user_id, role=role)
