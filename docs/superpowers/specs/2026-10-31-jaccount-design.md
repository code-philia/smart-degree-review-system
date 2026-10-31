# jAccount sign-in

Add campus sign-in to the existing authentication page and reuse the existing eight-hour application session. Preserve password sign-in, current users, role assignments and reports.

The supplied application accepts `essential` authorization and redirects to campus sign-in; `openid` and `basic` return `invalid_scope`. Therefore use the official authorization-code Profile API flow: authorization at jaccount.sjtu.edu.cn, a server-side token exchange, then Bearer-authenticated `/v1/me/profile` at api.sjtu.edu.cn. An OIDC ID-token flow would require a campus permission change and is unnecessary.

Use the fixed configured callback `http://121.36.247.138:3000/api/auth/jaccount/callback`. Bind each random state to an HttpOnly SameSite=Lax browser cookie, expire it after ten minutes and consume its database record atomically before exchanging the code. Never expose or persist provider tokens or client secrets.

Create a separate application identity keyed by the authenticated campus natural-person ID, with a `jaccount:` namespace. New identities receive STUDENT/COLLEGE access. Preserve any role already assigned by the application; never match or merge password users by an unverified name. Campus authentication does not confer application administrator access.

Keep the client ID, secret and callback in private server configuration. Use native Node fetch and crypto, with no new dependencies. Test against the documented provider envelope; verify the real authorization redirect before release. A real user's complete campus login still requires that user's interactive authentication.

References: https://developer.sjtu.edu.cn/auth/oidc.html ; https://developer.sjtu.edu.cn/api/profile.html ; https://developer.sjtu.edu.cn/api/overview.html
