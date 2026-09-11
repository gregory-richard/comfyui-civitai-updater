# Architecture

## High level

The plugin has three layers:

1. ComfyUI entrypoint (`__init__.py`)
2. Backend service (`comfy_updater/`)
3. Frontend sidebar tab (`js/civitai_updater.js`)

## Backend modules

- `plugin.py`: bootstraps the config store, archive store, job manager, and route registration
- `routes.py`: HTTP endpoints under `/civitai-updater/*`, the check-result cache, and merging of partial checks
- `jobs.py`: thread-based background job manager, result grouping, sorting, and the group outline
- `updater_service.py`: scan/check pipeline for one model file at a time
- `path_resolver.py`: resolve Comfy roots + `extra_model_paths.yaml` + custom roots, discover model files and orphan sidecars
- `hashing.py`: SHA256 file hashing
- `civitai_client.py`: Civitai API client with retries, preview download, and video frame extraction
- `sidecar.py`: sidecar file read/write helpers and corrupt-file quarantine
- `config_store.py`: persistent settings in `.civitai_updater/config.json`
- `archived_updates.py`: persistent list of hidden releases in `.civitai_updater/archived_updates.json`
- `base_models.py`: rolls Civitai base-model strings up into families for grouping
- `constants.py`: API URLs, supported types and extensions, sidecar suffixes, plugin version
- `node_info.py`: the status node, registered through both the legacy mappings and the V3 entrypoint

## Frontend module

`js/civitai_updater.js`:

- registers sidebar tab with `registerSidebarTab`
- registers native Comfy settings via `app.registerExtension({ settings: [...] })`
- syncs settings to backend config route
- starts/polls jobs and renders result cards with thumbnails
- reconnects to a running job after a page reload, and falls back to the
  on-disk cache when the server forgets a job (for example after a restart)

## Data flow

1. UI starts scan/check job via backend route.
2. Job manager launches a worker thread.
3. Updater service enumerates model files.
4. Service identifies files (sidecar ids, stored hash, or a fresh hash) and queries Civitai.
5. Sidecar files are updated.
6. Job output is polled by UI and rendered as result cards.
7. A finished check is written to `.civitai_updater/last_check.json`; a check
   limited to some model types replaces only those types in the file.

## Design constraints

- Keep v1 read-only regarding model file replacement.
- Keep sidecar files human-readable JSON.
- Keep Civitai auth optional.
- Never overwrite a user data file that failed to parse; move it aside first.
