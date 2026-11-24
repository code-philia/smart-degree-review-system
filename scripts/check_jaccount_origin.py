"""Check the public OAuth hand-off without signing in or logging state values."""
import argparse
from http.cookies import SimpleCookie
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_start(origin):
    expected = urlsplit(origin)
    if (expected.scheme not in ('http', 'https') or not expected.netloc
            or expected.username or expected.password or expected.path not in ('', '/')
            or expected.query or expected.fragment):
        raise ValueError('Expected an HTTP(S) origin without credentials or a path')
    origin = origin.rstrip('/')
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(origin + '/api/auth/jaccount', timeout=15)
    except HTTPError as error:
        response = error
    with response:
        issues = []
        if response.code != 302:
            issues.append('authorization_redirect_missing')
        provider = urlsplit(response.headers.get('Location', ''))
        if (provider.scheme, provider.netloc, provider.path) != (
                'https', 'jaccount.sjtu.edu.cn', '/oauth2/authorize'):
            issues.append('unexpected_authorization_destination')
        params = parse_qs(provider.query)
        callback = params.get('redirect_uri', [''])[0]
        if callback != origin + '/api/auth/jaccount/callback':
            issues.append('callback_origin_mismatch')
        state = params.get('state', [''])[0]
        cookies = SimpleCookie()
        for header in response.headers.get_all('Set-Cookie', []):
            cookies.load(header)
        matching = [c for name, c in cookies.items()
                    if name.startswith('arc_jaccount_state_') and c.value == state and state]
        if len(matching) != 1:
            issues.append('browser_state_cookie_missing')
        elif (matching[0]['domain'] or matching[0]['path'] != '/api/auth/jaccount'
                or not matching[0]['httponly'] or matching[0]['samesite'].lower() != 'lax'):
            issues.append('browser_state_cookie_scope_invalid')
        if matching and expected.scheme == 'https' and not matching[0]['secure']:
            issues.append('https_cookie_not_secure')
        if matching and expected.scheme == 'http' and matching[0]['secure']:
            issues.append('http_cookie_unusable')
        return {'origin': origin, 'ok': not issues, 'issues': issues}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origin', nargs='+')
    args = parser.parse_args()
    results = [check_start(origin) for origin in args.origin]
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(r['ok'] for r in results) else 1)
