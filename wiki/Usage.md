# Usage

## 1. Open panel

In ComfyUI, open sidebar tab `Civitai`.

## 2. Configure settings

Go to `Settings -> Civitai Updater`:

- API key (optional)
- timeout/retries/request delay
- path source toggles (Comfy defaults, `extra_model_paths.yaml`, custom paths)
- custom paths per model type

## 3. Quick workflow

1. Click `Check Updates`.
2. Watch progress bar and status.
3. Review `Updates Results` cards (update-only).
4. Use `Pause/Resume` or `Stop` for long jobs.

## 4. Scan workflow (Advanced)

Open `Advanced`, then run `Scan Metadata`.

- Scan only refreshes metadata sidecars.
- Scan report is compact (`total/refreshed/skipped/notFound/errors`).
- Scan does not fill update cards.
- After scan, run `Check Updates` to see updates.

## 5. Pagination and streaming

- Default page size is `25` (options: `25`, `50`, `100`).
- Metadata is polled every `800ms`.
- Page 1 auto-refreshes while a check job is running (streaming feel).
- If you navigate to another page, your page is preserved.

## 6. Result links

Each update card can show:

- `Model`
- `Release`
- `File URL`

`Version` means a specific Civitai release.
