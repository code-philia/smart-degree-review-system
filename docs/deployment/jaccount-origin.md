# jAccount public origin

The login page, authorization callback and session cookie must use the same browser origin. A state cookie issued by `https://thesis-review.sjtu.edu.cn` is not sent to a callback on `http://10.119.15.175`. This produces `jaccount_error=state` even after successful provider authentication.

Campus protected service configuration:

```dotenv
JACCOUNT_REDIRECT_URI=https://thesis-review.sjtu.edu.cn/api/auth/jaccount/callback
APP_PUBLIC_URL=https://thesis-review.sjtu.edu.cn
ARC_COOKIE_SECURE=1
```

Use `campus-origin.nginx.conf` for the campus gateway layout. It preserves the gateway's HTTPS indication and redirects old IP/port entry points to the public HTTPS domain, preserving the requested path and query. Loopback health/static checks remain available. Do not use this campus configuration on the independent external preview service, whose callback and public URL remain `http://121.36.247.138:3000` and whose HTTP cookies cannot be marked Secure.

After deployment run:

```sh
python3 scripts/check_jaccount_origin.py https://thesis-review.sjtu.edu.cn http://121.36.247.138:3000
```

The check creates an expiring login attempt without submitting credentials or calling the token endpoint. It checks the authorization destination, exact callback, host-only state cookie, HttpOnly/SameSite/path scope and Secure for HTTPS. Output excludes cookie values, OAuth state and client credentials. Complete provider authentication remains a separate interactive acceptance check.
