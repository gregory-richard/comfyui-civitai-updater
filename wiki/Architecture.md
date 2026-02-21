# Architecture

## High level

The plugin has three layers:

1. ComfyUI entrypoint (`__init__.py`)
2. Backend service (`comfy_updater/`)
3. Frontend sidebar tab (`js/civitai_updater.js`)

## Backend modules

- `plugin.py`: bootstraps config, jobs, and route registration
- `routes.py`: HTTP endpoints under `/civitai-updater/*`
- `jobs.py`: async background job manager
- `updater_service.py`: scan/check pipeline
- `path_resolver.py`: resolve Comfy roots + `extra_model_paths.yaml` + custom roots
- `hashing.py`: SHA256 file hashing
- `civitai_client.py`: Civitai API client with retries
- `sidecar.py`: sidecar file read/write helpers
- `config_store.py`: persistent settings in `.civitai_updater/config.json`

## Frontend module

`js/civitai_updater.js`:

- registers sidebar tab with `registerSidebarTab`
- registers native Comfy settings via `app.registerExtension({ settings: [...] })`
- syncs settings to backend config route
- starts/polls jobs and renders result cards with thumbnails

## Data flow

1. UI starts scan/check job via backend route.
2. Job manager launches worker thread.
3. Updater service enumerates model files.
4. Service hashes files and queries Civitai.
5. Sidecar files are updated.
6. Job output is polled by UI and rendered as result cards.

## Design constraints

- Keep v1 read-only regarding model file replacement.
- Keep sidecar files human-readable JSON.
- Keep Civitai auth optional.
- Keep existing A1111 code isolated in `legacy_a1111/`.
