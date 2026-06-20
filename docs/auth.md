# Latexed authentication

Latexed supports three explicit authentication modes:

- `AUTH_MODE=local` for local/dev and single-user deployments. The backend provisions `LOCAL_USER_ID` as a `User` row and ignores browser-supplied trusted identity headers.
- `AUTH_MODE=password` for first-class SaaS authentication. Use `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/logout-all`, and `/api/auth/me`.
- `AUTH_MODE=trusted_proxy` for enterprise reverse-proxy authentication. The proxy must strip browser-supplied `X-Latexed-User` and set the configured trusted identity header only after authenticating the user.

## Password auth

Password users store only bcrypt password hashes. Login creates an `auth_sessions` row and returns a short-lived JWT access token. Refresh tokens are high-entropy opaque strings; the database stores only HMAC hashes. Refresh rotates tokens by marking the old session `rotated` and creating a new active session in the same family. Reusing a rotated refresh token marks the family `compromised`.

Bootstrap the first password user with:

```bash
make create-user EMAIL=admin@example.com PASSWORD='replace-me' ROLE=admin
# or
cd backend && PYTHONPATH=. python -m app.cli.create_user --email admin@example.com --password 'replace-me' --role admin
```

For a single-user install that already owns data under `local-teacher`, adopt that id:

```bash
cd backend && PYTHONPATH=. python -m app.cli.create_user \
  --email admin@example.com \
  --password 'replace-me' \
  --role admin \
  --adopt-legacy-id local-teacher
```

## Production checklist

For `AUTH_MODE=password` in production:

- set a unique `SECRET_KEY`;
- set `AUTH_REFRESH_TOKEN_PEPPER`;
- keep `ACCESS_TOKEN_EXPIRE_MINUTES <= 60`;
- keep `REFRESH_TOKEN_EXPIRE_DAYS <= 90`;
- set `AUTH_COOKIE_SECURE=true` when cookie mode is enabled;
- keep `AUTH_REGISTRATION_ENABLED=false` unless you deliberately expose public registration.

All login, refresh, logout, trusted-proxy, and token-invalid events write rows to `auth_audit_logs` without raw passwords, access tokens, refresh tokens, or full authorization headers.
