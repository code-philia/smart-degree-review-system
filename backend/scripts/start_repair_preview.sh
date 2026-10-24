#!/usr/bin/env bash
set -euo pipefail

runtime_env="/data/projects/legacy-rule-repair-suggestions/runtime/repair-preview/backend.env"
if [[ ! -r "$runtime_env" ]]; then
  echo "Missing preview runtime configuration: $runtime_env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$runtime_env"
set +a
exec "$(dirname "$0")/../../../envs/node-v22.23.2/bin/node" "$(dirname "$0")/../src/index.js"
