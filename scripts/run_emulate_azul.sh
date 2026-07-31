#!/usr/bin/env bash
# Run the full Café→Azul chain into a versioned directory.
#
#   scripts/run_emulate_azul.sh <run_id>
#
# Never writes to modules/emulate_azul/results (the published baseline).
set -euo pipefail

RUN_ID="${1:?usage: run_emulate_azul.sh <run_id>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$REPO/modules/emulate_azul/_runs/$RUN_ID"

export AZUL_RUN_ID="$RUN_ID"
export AZUL_OUT_DIR="$RUN_DIR/results"
export AZUL_RENDERS_DIR="$RUN_DIR/renders"
mkdir -p "$AZUL_OUT_DIR" "$AZUL_RENDERS_DIR"

cd "$REPO"
CODE=modules/emulate_azul/code
STAGES=(build_v10_2 repair_v10_2_gain extract_tonal_repair finalize_v10_2_corrected improve_v11 improve_v12 improve_v13 improve_v14 improve_v15 improve_v16)
for stage in "${STAGES[@]}"; do
  echo "=== $RUN_ID :: $stage ==="
  python3 "$CODE/$stage.py"
done
echo "=== $RUN_ID :: done -> $RUN_DIR ==="
