import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# stdout is the detector's JSON protocol. PyMuPDF otherwise binds recoverable
# PDF syntax diagnostics to stdout when it is imported, before detect() runs.
# The import-time setting also supports the minimum PyMuPDF 1.24 dependency.
os.environ["PYMUPDF_MESSAGE"] = "fd:2"

from pdf_rules.engine import detect


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--rule", action="append", required=True, type=int)
    args = parser.parse_args()
    result = detect(args.pdf, args.rule)
    # Escape isolated font surrogates while preserving their JSON values.
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
