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
    # Escape isolated font surrogates while preserving their JSON values.
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
