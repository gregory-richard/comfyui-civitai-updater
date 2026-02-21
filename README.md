# Civitai Updater for ComfyUI

ComfyUI custom node plugin focused on update visibility for local Civitai models.

This repository is ComfyUI-first. Legacy A1111 code is archived in `legacy_a1111/`.

## Core UX

- `Results` is update-check only.
- `Quick Actions` is minimal: `Check Updates`, `Pause/Resume`, `Stop`.
- `Advanced` (collapsed by default) contains model scope, scan, and force-rehash options.
- Long update lists are paginated (25/50/100) using backend paging.
- Scan report is compact and separate from update cards.

## Scan vs Check

- `Scan Metadata`:
  - refreshes sidecar metadata
  - reports `total/refreshed/skipped/notFound/errors`
  - does not populate update cards
- `Check Updates`:
  - compares local release with latest Civitai release
  - populates update cards and counts

`Version` = a specific Civitai release of a model.

## Installation

1. Put this repo under ComfyUI `custom_nodes` (or create a junction/symlink).
2. Restart ComfyUI.
3. Open `Civitai` in the sidebar.

Windows junction example:

```powershell
$src = "C:\Users\grego\Documents\Coding\civitai-updater"
$dst = "C:\Users\grego\Documents\StableDiffusion\ComfyUI-2602\custom_nodes\civitai-updater"
New-Item -ItemType Junction -Path $dst -Target $src
```

## Settings

Use `Settings -> Civitai Updater`.

- API key (optional)
- timeout / retries / per-model delay
- path source toggles:
  - Comfy default paths
  - `extra_model_paths.yaml`
  - custom paths
- custom paths per model type

## API Snapshot

- `GET /civitai-updater/config`
- `POST /civitai-updater/config`
- `POST /civitai-updater/jobs/scan`
- `POST /civitai-updater/jobs/check-updates`
- `GET /civitai-updater/jobs/{job_id}` (metadata + `itemCount`)
- `GET /civitai-updater/jobs/{job_id}/items?offset&limit&mode=updates`
- `POST /civitai-updater/jobs/{job_id}/pause`
- `POST /civitai-updater/jobs/{job_id}/resume`
- `POST /civitai-updater/jobs/{job_id}/stop`

## Styling Choice

This plugin uses handcrafted CSS (Civitai-inspired palette) and avoids Tailwind for now:

- easier static distribution in Comfy custom nodes
- no frontend build toolchain overhead
- no runtime CDN dependency
