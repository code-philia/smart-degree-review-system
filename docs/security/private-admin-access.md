# Campus sign-in and private administrator access

Production browser access uses jAccount by default. The public login page contains no visible local password form or local-account recovery/help links. A jAccount identity is separate from a same-named password account and cannot sign in with a school or college administrator role.

## Owner-requested trial access

Clicking the university emblem in the login-page masthead opens a dialog for the four existing trial identities: `student01`, `supervisor01`, `college_admin01`, and `school_admin01`. The login-page Pilot V0.9 label is removed. Their existing database passwords, roles and data scopes remain authoritative; no credentials appear in the frontend bundle or help text. The emblem trigger also supports keyboard focus/activation; credentials are cleared when the dialog closes.

Public trial access is disabled unless `ARC_TRIAL_LOGIN_ENABLED=1` and either `ARC_TRIAL_LOGIN_ORIGINS` or the legacy `ARC_TRIAL_LOGIN_ORIGIN` are explicitly configured. The legacy setting must be the site's exact HTTP(S) origin, for example `http://121.36.247.138:3000`.

For multiple approved entry points, set `ARC_TRIAL_LOGIN_ORIGINS` to a comma-separated list of exact HTTP(S) origins. For the campus IP and official domain:

```text
ARC_TRIAL_LOGIN_ORIGINS=http://10.119.15.175,https://thesis-review.sjtu.edu.cn
```

When present, this list replaces the legacy single-origin setting. An empty or invalid list disables trial access; it does not fall back to the legacy value. URLs with credentials, paths, queries or fragments are rejected. Requests still require an Origin in the list and a Host matching that particular Origin; being separately listed does not permit mixing one entry's Origin with another entry's Host. Configure each deployment explicitly; adding the campus domain here does not enable it on other servers.

The separate `POST /api/auth/trial-login` endpoint requires same-origin JSON, a trusted Host and an exact trial user ID/name/role match. A process-local bounded limiter allows five attempts per TCP-peer/account pair and twenty per TCP peer in fifteen minutes; spoofed forwarding headers do not change the peer. Trial sessions have a server-created `trial:` random-ID prefix and the usual HttpOnly/SameSite cookie. Prefixing an existing cookie cannot produce a valid database session. Disabling the feature or changing a trial identity's expected role immediately rejects that session.

This is an explicit exception to campus-only access requested by the owner. The hidden label is not a security boundary: anyone with valid trial credentials has that trial account's existing permissions. Other local accounts and old private administrator sessions remain rejected by the public listener.

## Public authentication boundary

- Production always enforces campus-only public authentication. `ARC_AUTH_MODE=jaccount-only` enables the same policy in development and tests; a legacy value cannot disable the production policy.
- Public `POST /api/auth/login` returns 403 before checking a password or creating a session.
- Public session restoration and protected APIs accept non-administrator jAccount identities and explicitly enabled, newly authenticated trial sessions. Other existing local-account cookies and private administrator cookies cannot grant public access.
- Accounts, assigned roles, password hashes, reports and existing session records are retained; access is checked against the listener on every request.

## Private administrator API

The same service additionally binds `127.0.0.1:3002` in production. `ARC_ADMIN_PORT` can select another valid port distinct from `PORT`. The public website continues to use port 3000.

Only password accounts with `SCHOOL_ADMIN` or `COLLEGE_ADMIN` roles may use private `POST /api/auth/login`. It checks the actual TCP local port and loopback peer, not forwarding headers. Requests with untrusted Host or cross-origin browser headers are rejected. A public reverse proxy forwarding to port 3000 does not grant access to the private listener.

On the server, submit administrator credentials to:

```text
POST http://127.0.0.1:3002/api/auth/login
Content-Type: application/json

{"username":"YOUR_ADMIN_ACCOUNT","password":"YOUR_ADMIN_PASSWORD"}
```

The response sets the existing HttpOnly `arc_session` cookie. Use that cookie for subsequent requests to the private listener; it does not authenticate requests on the public listener.

For remote administration, use an authenticated SSH tunnel with a local loopback binding:

```sh
ssh -N -L 127.0.0.1:8768:127.0.0.1:3002 YOUR_SSH_HOST
```

Then send the same API request to `http://127.0.0.1:8768/api/auth/login`. This API is intentionally not advertised on the public login page.

## Verification

`backend/tests/auth-private-admin.integration.test.js` covers public password rejection, forged forwarding headers, both private administrator roles, ordinary-account rejection, session replay across listeners, untrusted browser hosts/origins, same-name jAccount isolation, and rejection of existing campus administrator roles. Frontend auth tests cover the single jAccount entry and preservation of the selected campus illustration and interactions.
