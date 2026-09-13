#!/bin/sh
# Open the self-contained farm demo and register this checkout for this session.
set -eu
TCITY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TCITY_DEMO=TCity_Taiwan_Farmland.blend
if [ "${1:-}" = "--village" ]; then
    TCITY_DEMO=TCity_Taiwan_Village.blend
    shift
fi
for TCITY_RUNTIME in "$TCITY_ROOT"/.venv/lib/python*/site-packages; do
    if [ -d "$TCITY_RUNTIME/cattrs" ]; then
        export PYTHONPATH="$TCITY_RUNTIME${PYTHONPATH:+:$PYTHONPATH}"
        break
    fi
done
exec blender --python-use-system-env "$TCITY_ROOT/dist/$TCITY_DEMO" \
    --python "$TCITY_ROOT/scripts/register_local.py" "$@"
