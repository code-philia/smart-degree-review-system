import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdf_rules.engine import detect


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--rule", action="append", required=True, type=int)
    args = parser.parse_args()
    result = detect(args.pdf, args.rule)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
