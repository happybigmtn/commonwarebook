#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="$ROOT_DIR/fabro/runs/book"
MODE="plan"
MAX_PARALLEL="${MAX_PARALLEL:-3}"

usage() {
  cat <<'EOF'
Usage:
  fabro/scripts/dispatch-book-batch.sh [--preflight|--execute] [module...]

Modes:
  default      Print the commands that would run.
  --preflight  Run `fabro run <config> --preflight` for each selected module.
  --execute    Actually dispatch the selected configs in parallel.

Examples:
  fabro/scripts/dispatch-book-batch.sh
  fabro/scripts/dispatch-book-batch.sh --preflight
  fabro/scripts/dispatch-book-batch.sh --execute runtime consensus
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--preflight" ]]; then
  MODE="preflight"
  shift
elif [[ "${1:-}" == "--execute" ]]; then
  MODE="execute"
  shift
fi

declare -a CONFIGS=()
if [[ "$#" -eq 0 ]]; then
  while IFS= read -r cfg; do
    CONFIGS+=("$cfg")
  done < <(find "$RUN_DIR" -maxdepth 1 -name '*.toml' | sort)
else
  for module in "$@"; do
    cfg="$RUN_DIR/${module}.toml"
    if [[ ! -f "$cfg" ]]; then
      echo "Missing run config: $cfg" >&2
      exit 1
    fi
    CONFIGS+=("$cfg")
  done
fi

echo "Mode: $MODE"
echo "Max parallel: $MAX_PARALLEL"
echo "Selected configs:"
for cfg in "${CONFIGS[@]}"; do
  echo "  - ${cfg#$ROOT_DIR/}"
done

case "$MODE" in
  plan)
    echo
    echo "Commands that would run:"
    for cfg in "${CONFIGS[@]}"; do
      printf '  fabro run %q\n' "${cfg#$ROOT_DIR/}"
    done
    ;;
  preflight)
    for cfg in "${CONFIGS[@]}"; do
      echo
      echo "==> Preflight ${cfg#$ROOT_DIR/}"
      (cd "$ROOT_DIR" && fabro run "${cfg#$ROOT_DIR/}" --preflight)
    done
    ;;
  execute)
    printf '%s\0' "${CONFIGS[@]}" | xargs -0 -n 1 -P "$MAX_PARALLEL" -I {} bash -lc '
      set -euo pipefail
      cd "'"$ROOT_DIR"'"
      echo "==> Running ${1#'"$ROOT_DIR"'/}"
      fabro run "${1#'"$ROOT_DIR"'/}"
    ' _ {}
    ;;
esac
