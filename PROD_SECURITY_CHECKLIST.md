# Production Security Checklist

## Required Runtime Configuration
- Set `APP_ENV=production`.
- Set strong `SECRET_KEY` (32+ chars, random).
- Set strong `MCP_SHARED_TOKEN` (32+ chars, random).
- Set `ADMIN_BOOTSTRAP_TOKEN` and rotate regularly.
- Set explicit `ALLOWED_ORIGINS` for trusted frontends.
- Set `JWT_ISSUER` and `JWT_AUDIENCE` to deployment values.

## Auth and Provisioning
- Do not allow public privileged role registration.
- Require bootstrap token for machine registration and elevated user roles.
- Enforce TOTP-based MFA for step-up authentication.
- Enforce rate limits on authorize/token/mfa/register endpoints.

## Token and Session Controls
- Keep access token lifetime short.
- Validate JWT issuer/audience in every protected endpoint.
- Include `jti` and maintain revocation records.
- Deny requests using revoked tokens.

## API and Browser Hardening
- Restrict CORS origins, methods, and headers in production.
- Do not persist bearer tokens in browser storage.
- Treat MFA bootstrap secrets as one-time enrollment material; never log or persist them in the browser.
- Return generic error details to clients for internal failures.
- Keep audit logs structured and avoid sensitive content.

## CI and Release Gates
- Run tests on every PR and main push.
- Run dependency vulnerability scanning.
- Run static security scan (`bandit`) on backend code.
- Run container/filesystem vulnerability scan (`trivy`).
- Block merges when any security gate fails.

## Deployment Controls
- Run containers as non-root.
- Keep DB and internal service ports private to network.
- Add health checks for service dependencies.
- Rotate all auth-related secrets on a fixed cadence.
