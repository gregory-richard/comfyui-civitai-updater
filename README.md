# Civitai Updater for ComfyUI

![Civitai Updater Banner](assets/registry/banner.png)

ComfyUI custom node extension focused on update visibility for local Civitai models.

![Civitai Updater Sidebar Panel](assets/docs/panel-sidebar.png)

## Core UX

- `Check for Updates` scans files and compares local model versions with latest Civitai releases.
- `Scan Metadata Only` scans files and refreshes sidecar metadata only.
- Results are paginated (25/50/100), filterable, and can hide specific remote versions.
- Long jobs support `Pause/Resume` and `Stop`.

`Version` means a specific Civitai release of a model.
`New` is now date-based: a remote version is shown only when its `publishedAt` date, or `createdAt` when `publishedAt` is missing, is newer than the newest installed local version date for that model.

## Installation

1. Put this repo under ComfyUI `custom_nodes` (or create a junction/symlink).
2. Restart ComfyUI.
3. Open `Civitai` in the sidebar.

Windows junction example:

```powershell
$src = "C:\Users\grego\Documents\Coding\comfyui-civitai-updater"
$dst = "C:\Users\grego\Documents\StableDiffusion\ComfyUI-2602\custom_nodes\comfyui-civitai-updater"
New-Item -ItemType Junction -Path $dst -Target $src
```

## Settings

Use `Settings -> Civitai Updater`.

- API key (optional)
- cache TTL
- timeout / retries / per-model delay
- treat valid `.civitai.info` sidecars as installed models (enabled by default)
- path sources:
  - Comfy default paths
  - `extra_model_paths.yaml`
  - custom paths per model type

When sidecar-only tracking is enabled, an orphan `.civitai.info` file with valid
Civitai `modelId` and version `id` fields counts as an installed version for
update comparisons. Preview PNGs do not count by themselves, and malformed or
incomplete sidecars are ignored.

## API Snapshot

- `GET /civitai-updater/config`
- `POST /civitai-updater/config`
- `POST /civitai-updater/jobs/scan`
- `POST /civitai-updater/jobs/check-updates`
- `GET /civitai-updater/jobs/{job_id}`
- `GET /civitai-updater/jobs/{job_id}/items?offset&limit&mode=updates&showHidden=0|1&modelType=...&baseModel=...`
- `POST /civitai-updater/archived-updates`
- `POST /civitai-updater/archived-updates/restore`
- `POST /civitai-updater/jobs/{job_id}/pause`
- `POST /civitai-updater/jobs/{job_id}/resume`
- `POST /civitai-updater/jobs/{job_id}/stop`

## Attribution

This project was built based on:
- https://github.com/zixaphir/Stable-Diffusion-Webui-Civitai-Helper

## AI Tooling Disclosure

This extension was primarily created with AI-assisted development using:
- GPT-5.3-Codex
- Claude Opus 4.6
