#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTDIR="$ROOT/artifacts"
mkdir -p "$OUTDIR"
ZIP_PATH="$OUTDIR/paper-model-mutant-code.zip"

python3 - "$ROOT" "$ZIP_PATH" <<'PY'
import os
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
files = [
    root / 'backend/scripts/paper_model_bilingual_rules.py',
    root / 'backend/scripts/build_bilingual_mutation_cases.py',
    root / 'backend/paper_compiler/mutations.py',
    root / 'backend/paper_compiler/online_mutants.py',
]

missing = [str(p) for p in files if not p.exists()]
if missing:
    raise FileNotFoundError(f"Missing required files: {missing}")

out.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for p in files:
        arcname = p.relative_to(root)
        zf.write(p, arcname.as_posix())

    readme = """Paper Model Mutant Code Pack
=================================

This archive includes the relevant code for constructing paper-model-based mutants.

Included files:
- backend/scripts/paper_model_bilingual_rules.py
- backend/scripts/build_bilingual_mutation_cases.py
- backend/paper_compiler/mutations.py
- backend/paper_compiler/online_mutants.py

Purpose:
- extract paper-model facts from the PDF/IR
- construct bilingual mutation cases from the paper model
- apply low-level IR mutations
- verify online mutant cases in benchmark flow
"""
    zf.writestr('paper-model-mutant-code/README.txt', readme)

print(f"Created zip: {out}")
PY
