# Campus sign-in and private administrator access

Production browser access uses jAccount. The public login page contains no local password form or local-account recovery/help links. A jAccount identity is separate from a same-named password account and cannot sign in with a school or college administrator role.

## Public authentication boundary

- Production always enforces campus-only public authentication. `ARC_AUTH_MODE=jaccount-only` enables the same policy in development and tests; a legacy value cannot disable the production policy.
- Public `POST /api/auth/login` returns 403 before checking a password or creating a session.
- Public session restoration and protected APIs accept only non-administrator jAccount identities. Existing local account cookies and administrator cookies cannot grant public access.
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
