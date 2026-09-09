#!/bin/sh
# Local convenience launcher; does not install add-ons or save preferences.
set -eu
TCITY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# This workstation's packaged Blender is missing cattrs. Reuse project-local
# build dependencies when present; official Blender builds do not need this.
for TCITY_RUNTIME in "$TCITY_ROOT"/.venv/lib/python*/site-packages; do
    if [ -d "$TCITY_RUNTIME/cattrs" ]; then
        export PYTHONPATH="$TCITY_RUNTIME${PYTHONPATH:+:$PYTHONPATH}"
        break
    fi
done
exec blender --python-use-system-env "$TCITY_ROOT/dist/TCity_Taiwan_District.blend" \
    --python "$TCITY_ROOT/scripts/register_local.py" "$@"
