from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from business_brain.security.auth0 import Auth0TokenValidator, TokenValidationError
from business_brain.security.context import UserRole

DOMAIN = "example.us.auth0.com"
AUDIENCE = "https://api.aura-business-brain.demo"
TENANT_CLAIM = "https://business-brain.demo/tenant_id"
ROLE_CLAIM = "https://business-brain.demo/role"
KID = "test-key-1"


@pytest.fixture
def signing_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return private_key, jwk


def make_token(private_key, **overrides):
    now = datetime.now(UTC)
    claims = {
        "sub": "auth0|demo-cfo",
        "iss": f"https://{DOMAIN}/",
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        TENANT_CLAIM: "tenant_aura",
        ROLE_CLAIM: "founder_cfo",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def make_validator(jwk, calls):
    async def fetcher(url):
        calls.append(url)
        return {"keys": [jwk]}

    return Auth0TokenValidator(
        domain=DOMAIN,
        audience=AUDIENCE,
        tenant_claim=TENANT_CLAIM,
        role_claim=ROLE_CLAIM,
        jwks_fetcher=fetcher,
    )


@pytest.mark.asyncio
async def test_valid_token_maps_immutable_identity_and_caches_jwks(signing_material) -> None:
    private_key, jwk = signing_material
    calls = []
    validator = make_validator(jwk, calls)

    first = await validator.validate(make_token(private_key))
    second = await validator.validate(make_token(private_key))

    assert first == second
    assert first.tenant_id == "tenant_aura"
    assert first.user_id == "auth0|demo-cfo"
    assert first.role is UserRole.FOUNDER_CFO
    assert calls == [f"https://{DOMAIN}/.well-known/jwks.json"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"aud": "wrong-audience"},
        {"iss": "https://wrong.example/"},
        {"exp": datetime.now(UTC) - timedelta(minutes=2)},
        {TENANT_CLAIM: "INVALID TENANT"},
        {ROLE_CLAIM: "administrator"},
        {ROLE_CLAIM: ["founder_cfo", "staff_accountant"]},
    ],
)
async def test_invalid_token_or_identity_claim_is_rejected(
    signing_material,
    claim_overrides,
) -> None:
    private_key, jwk = signing_material
    validator = make_validator(jwk, [])

    with pytest.raises(TokenValidationError):
        await validator.validate(make_token(private_key, **claim_overrides))


@pytest.mark.asyncio
async def test_unknown_signing_key_is_rejected(signing_material) -> None:
    private_key, jwk = signing_material
    jwk["kid"] = "different-key"
    validator = make_validator(jwk, [])

    with pytest.raises(TokenValidationError):
        await validator.validate(make_token(private_key))
