# Development

## Local structure

- backend: `comfy_updater/`
- frontend: `js/civitai_updater.js`
- docs: `README.md`, `wiki/`

## Run in ComfyUI

1. Link repo into Comfy `custom_nodes`.
2. Restart ComfyUI after code changes.
3. Open browser devtools for frontend issues.
4. Check Comfy terminal logs for backend route/job issues.

## Sidecar behavior

Files written beside model files:

- `.civitai.info`
- `.civitai.state.json`

These are the cache layer for scan/check results.

## Compatibility target

Current implementation follows modern Comfy frontend extension APIs (`registerSidebarTab`) and backend route registration through `PromptServer`.

