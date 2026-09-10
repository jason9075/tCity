#!/bin/sh
# Open the self-contained modern community demo and register this checkout for this session.
set -eu
TCITY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for TCITY_RUNTIME in "$TCITY_ROOT"/.venv/lib/python*/site-packages; do
    if [ -d "$TCITY_RUNTIME/cattrs" ]; then
        export PYTHONPATH="$TCITY_RUNTIME${PYTHONPATH:+:$PYTHONPATH}"
        break
    fi
done
exec blender --python-use-system-env "$TCITY_ROOT/dist/TCity_Modern_Communities.blend" \
    --python "$TCITY_ROOT/scripts/register_local.py" "$@"
