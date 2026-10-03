# Auth0 setup for Business Brain

The API accepts Auth0 access tokens only when `AUTH_MODE=auth0`. It validates the
RS256 signature against the tenant JWKS, plus issuer, audience, expiry, subject,
tenant, and exactly one supported application role.

## 1. Register the API

In Auth0 Dashboard, open **Applications > APIs > Create API**:

- Name: `Aura Business Brain API`
- Identifier: `https://api.aura-business-brain.demo`
- Signing algorithm: `RS256`

Enable **RBAC** and **Add Permissions in the Access Token** in the API settings.

## 2. Create application roles

Under **User Management > Roles**, create these exact role names:

- `founder_cfo`
- `logistics_manager`
- `staff_accountant`
- `support_intern`

Each demo user must have exactly one of these roles.

## 3. Add immutable identity claims

Create a Post Login Action named `Business Brain identity claims`, deploy it,
and add it to the Login flow:

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const namespace = "https://business-brain.demo";
  const tenantId = event.user.app_metadata?.tenant_id;
  const roles = event.authorization?.roles ?? [];

  if (tenantId) {
    api.accessToken.setCustomClaim(`${namespace}/tenant_id`, tenantId);
  }
  api.accessToken.setCustomClaim(`${namespace}/role`, roles);
};
```

Set each user's `app_metadata` to either:

```json
{"tenant_id": "tenant_aura"}
```

or, for the adversarial tenant:

```json
{"tenant_id": "tenant_apex"}
```

Do not use editable `user_metadata` for authorization claims.

## 4. Configure the local API

Copy the Auth0 Domain and API Identifier into the uncommitted `.env` file:

```dotenv
AUTH_MODE=auth0
AUTH0_DOMAIN=your-tenant-region.auth0.com
AUTH0_AUDIENCE=https://api.aura-business-brain.demo
AUTH0_CLIENT_ID=your-public-spa-client-id
AUTH0_TENANT_CLAIM=https://business-brain.demo/tenant_id
AUTH0_ROLE_CLAIM=https://business-brain.demo/role
```

No Auth0 client secret is required by this backend. The future browser client
will use a public Client ID with Authorization Code plus PKCE.

## 5. Verify

After logging in through an Auth0 application that requests the API audience,
call:

```text
GET /api/v1/auth/me
Authorization: Bearer <access-token>
```

For the pre-frontend live check, allow `http://127.0.0.1:8765/callback` in the
SPA and run `uv run python scripts/verify_auth0_login.py`. Open the displayed
authorization URL and sign in. The script validates the returned access token
and prints only the derived identity; it never prints or stores the token.

The response or verification output must show the token-derived tenant, Auth0
subject, and role. Mock identity headers are ignored in Auth0 mode.
