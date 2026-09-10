# TCity dev asset packaging.
#
# `dist/` holds release ZIPs and demo .blend files (see build_demo.py /
# build_modern_demo.py). It's gitignored because those are large, regenerable
# build products — but regenerating everything from scratch on a new machine
# means re-running every build/render script. These recipes just zip up the
# current dist/ as-is so it can be copied to another machine and dropped back
# in place.
#
# Usage:
#   just package-assets                  # -> assets-archive/tcity-assets-<version>.zip
#   just import-assets path/to/that.zip  # unzips into dist/ on the new machine

version := `grep '^version' tcity/blender_manifest.toml | sed -E 's/version = "(.*)"/\1/'`
root := justfile_directory()
archive_dir := root / "assets-archive"
assets_zip := archive_dir / "tcity-assets-" + version + ".zip"

# List available recipes.
default:
    @just --list

# Zip up dist/ (release ZIPs + demo .blend files) for transfer to another machine.
# Skips .blend1 backups and generated test-report JSON — those aren't worth shipping.
package-assets output=assets_zip:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d "{{root}}/dist" ] || [ -z "$(ls -A "{{root}}/dist" 2>/dev/null)" ]; then
        echo "dist/ is empty — build something first (see scripts/build_demo.py, build_modern_demo.py)." >&2
        exit 1
    fi
    mkdir -p "{{archive_dir}}"
    rm -f "{{output}}"
    cd "{{root}}/dist" && zip -rq -X "{{output}}" . \
        -x '*.blend1' -x '*_results.json' -x 'test_results.json'
    echo "Packed dist/ -> {{output}}"
    du -h "{{output}}"

# Unzip a previously packaged assets archive back into dist/ (overwrites matching files).
import-assets archive:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f "{{archive}}" ]; then
        echo "No such archive: {{archive}}" >&2
        exit 1
    fi
    mkdir -p "{{root}}/dist"
    unzip -oq "{{archive}}" -d "{{root}}/dist"
    echo "Imported {{archive}} -> dist/"
    just list-assets

# Show what's currently in dist/ that package-assets would pick up.
list-assets:
    @find "{{root}}/dist" -type f \( -name '*.zip' -o -name '*.blend' \) | sort | xargs -r ls -lh
