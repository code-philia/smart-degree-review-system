# Hidden trial sign-in implementation plan

**Goal:** Clicking the existing version label opens a restrained login dialog for the four existing trial accounts, as explicitly requested by the owner.

**Architecture:** Keep jAccount as the visible default. Use a separately enabled, same-origin trial endpoint, exact ID/name/role allowlisting, existing password verification and permission checks, and tagged random server sessions. Preserve existing accounts, passwords, reports and private administrator access.

**Stack:** Existing React, Radix Dialog, Axios, Express, bcrypt and SQLite; no new dependencies.

1. Add failing integration tests for all four roles, disabled configuration, bad credentials, cross-origin requests, throttling, cookie forgery, session revocation and preserved private/public boundaries.
2. Add the trial policy/endpoint and tagged-session checks without schema changes; run the authentication regressions.
3. Add failing frontend tests for the hidden trigger, focused password form, successful role-specific session, errors, duplicate submissions and dismissal. Implement the dialog with the existing session provider and warm campus styles.
4. Run the related frontend tests and production build; review independently and push the English Conventional Commit to main from the server using the owner's GitHub identity.

The version label is a discovery affordance, not an authorization control. This deliberately permits the four password-authenticated trial identities on the public listener; unrelated local accounts, old private administrator sessions and campus identities cannot acquire trial access. Activation requires explicit runtime configuration. Deployment follows the workspace's explicit-authorization rule.
