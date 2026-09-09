# Repository Guidelines

## Project Structure & Module Organization

`tcity/` is the Blender 5.2 add-on package. `nodes.py` builds the main Geometry Nodes graph; `residential.py`, `sheds.py`, and `street_assets.py` create assets; `infrastructure.py` handles streets and utilities; and `__init__.py` exposes operators and UI. Bundled runtime resources live under `tcity/fonts/` and `tcity/environment/`.

`tests/` contains Blender integration and packaging tests. `scripts/` holds demo-building, rendering, local registration, and font-subsetting utilities. Research and planning notes belong in `docs/`; rendered previews belong in `renders/`. `dist/` contains release ZIPs, demo `.blend` files, archived versions, and generated test reports. Treat `build/` as disposable output.

## Build, Test, and Development Commands

- `./scripts/open_demo.sh` opens the packaged demo and loads the checkout's sidebar for that Blender session.
- `blender -b --factory-startup --python-exit-code 1 --python scripts/build_demo.py -- --render` rebuilds the demo and reference renders.
- `blender -b --factory-startup --python-exit-code 1 --python tests/test_blender.py` runs core evaluated-geometry integration tests.
- Run the same Blender command with `tests/test_infrastructure.py`, `test_package.py`, `test_upgrade.py`, or `test_demo.py` for focused suites.
- `blender --command extension build --source-dir tcity --output-dir dist` builds the extension ZIP; validate it with `blender --command extension validate dist/tcity-<version>.zip`.

## Coding Style & Naming Conventions

Use Python with four-space indentation and standard `snake_case` functions and variables; use `UPPER_CASE` for constants and Blender-style descriptive object names where established. No formatter or linter is configured, so match nearby code and keep Blender API operations explicit. Keep resource paths relative to the repository via `pathlib.Path`. Do not add runtime dependencies without confirming they work inside Blender's bundled Python.

## Testing Guidelines

Tests are executable Blender scripts built around assertions, not pytest. Name new files `tests/test_<feature>.py`, start from `--factory-startup`, and make seeded procedural results deterministic. Validate evaluated depsgraph output and geometry, not merely node existence. Write generated JSON reports only to `dist/`. Run the focused suite plus `test_blender.py` before submitting changes; packaging changes also require `test_package.py` and extension validation.

## Commit & Pull Request Guidelines

This repository has no commit history yet. Use short, imperative subjects such as `Add utility pole spacing control`, and keep each commit focused. Pull requests should explain user-visible behavior, list Blender version and commands run, link relevant issues or research, and include before/after screenshots for geometry, material, UI, or render changes. Do not commit caches, `.blend1` backups, `.venv/`, or `build/` output.
