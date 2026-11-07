"""Probe the R32 Scholar route with a synthetic query; never print credentials."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.evidence import EvidenceGateway
from paper_compiler.serpapi_scholar import SerpApiScholar, SerpApiError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Make real Scholar requests using service credentials (may consume quota).')
    args = parser.parse_args()
    requests = []
    original = SerpApiScholar._request
    def transport(self, url):
        requests.append(urlsplit(url).hostname)
        return original(self, url) if args.live else (429, b'{"error":"Your account has run out of searches."}')
    SerpApiScholar._request = transport
    import os
    # Always isolate the probe from the production library and quota marker.
    with tempfile.TemporaryDirectory(prefix='serpapi-probe-') as directory:
        os.environ['PAPER_COMPILER_REFERENCE_LIBRARY'] = directory
        if not args.live:
            os.environ['SERPAPI_API_KEY'] = 'synthetic-test-key'
        gateway = EvidenceGateway(Path(directory) / 'gateway', providers=[], live_providers='crossref')
        result = {'provider': 'serpapi', 'live': args.live}
        try:
            records = gateway.lookup_rule32({'title': 'Attention Is All You Need', 'authors': ['Vaswani'], 'year': 2017})
            result['status'] = 'matched' if any(r.get('status') == 'ok' for r in records) else 'not_matched'
        except SerpApiError as error:
            code = str(error)
            result['status'] = 'quota_exhausted' if code == 'SERPAPI_QUOTA_EXHAUSTED' else 'provider_unavailable'
        except Exception:
            result['status'] = 'probe_failed'
        result['request_count'] = len(requests)
        result['request_hosts'] = sorted(set(requests))
        print(json.dumps(result))


if __name__ == '__main__':
    main()
