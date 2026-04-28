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

1. Click `Scan + Check Updates`.
2. Watch progress bar and status.
3. Review `Updates Results` cards (update-only).
4. Use the multi-select `Types` and `Bases` filters, plus `Show hidden`, to narrow the result list.
5. Use `Pause/Resume` or `Stop` for long jobs.

## 4. Scan workflow (Advanced)

Open `Advanced`, then run `Scan Only (Metadata)`.

- Scan only refreshes metadata sidecars.
- Scan report is compact (`total/refreshed/skipped/notFound/errors`).
- Scan does not fill update cards.
- After scan, run `Scan + Check Updates` to see updates.

## 5. Pagination and streaming

- Default page size is `25` (options: `25`, `50`, `100`).
- Metadata is polled every `800ms`.
- Page 1 auto-refreshes while a check job is running (streaming feel).
- While a check job is still running, cards are marked `Provisional` because another local file for the same model can still change which remote versions count as new.
- If you navigate to another page, your page is preserved.

## 6. Result links

Each update card can show:

- `Model`
- `Saved` local versions
- multiple `New` remote versions, sorted by release date descending
- `File URL`

`Version` means a specific Civitai release.
`New` uses Civitai release dates: `publishedAt` first, then `createdAt` when `publishedAt` is missing.

## 7. Hidden updates

- Use `Hide` on a remote version row if you do not want to download that version.
- Hidden versions stay hidden across future checks.
- Enable `Show hidden` to review or unarchive them later.
