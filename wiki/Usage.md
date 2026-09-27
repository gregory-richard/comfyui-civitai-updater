# Usage

## 1. Open panel

In ComfyUI, open sidebar tab `Civitai`.

## 2. Configure settings

Go to `Settings -> Civitai Updater`:

- API key (optional)
- cache duration (how long `Check for Updates` shows saved results instead of checking again)
- timeout/retries/request delay
- treat valid `.civitai.info` sidecars as installed models (enabled by default)
- path source toggles (Comfy defaults, `extra_model_paths.yaml`, custom paths)
- custom paths per model type
- mature content (show, blur previews, hide)

## 3. Quick workflow

1. Click `Check for Updates`.
2. Watch progress bar and status.
3. Review the `Results` cards. The `Updates` view lists models with a newer
   release; `Issues` lists the models Civitai could not match or check, with the
   reason under each file.
4. Use the multi-select `Types` and `Bases` filters, plus `Show hidden`, to narrow the result list.
5. Use `Pause/Resume` or `Stop` for long jobs. `Stop` waits at most for the
   request in flight; a file being hashed is abandoned.
6. Limit the **Model Scope** in the panel settings to re-check only some types; results for the other types are kept from the previous check.

Within the cache duration, `Check for Updates` shows the saved results instead
of checking again, unless Model Scope differs from the last check, files were
added or removed, `Force rehash` is ticked, or the last check was stopped.
`Refresh` next to "Last checked" always runs a check.

## 4. Metadata workflow (Advanced)

Run `Fetch Missing Metadata`.

- Downloads `.civitai.info` sidecars and preview images only.
- Models that already have a sidecar are skipped, unless `Refetch metadata that
  already exists` is ticked — that re-pulls them by sidecar version ID, with no
  re-hashing.
- Never queries the version list, so it never reports updates and never fills
  update cards.
- Report is compact (`total/refreshed/skipped/notFound/errors`).
- Use it to populate names, base models, and thumbnails after adding a batch of
  models, then run `Check for Updates` to see what is outdated.

## 5. Pagination and streaming

- Default page size is `25` (options: `25`, `50`, `100`).
- Metadata is polled every `800ms`.
- Page 1 auto-refreshes while a check job is running (streaming feel).
- While a check job is running, a card built from the previous check's results is marked `Provisional` until its files have been re-checked.
- If you navigate to another page, your page is preserved.

## 6. Reading a result card

Each card is a ledger of one model's releases. The dot on the left of every row
says where that version stands:

| Dot | Row | Meaning |
| --- | --- | --- |
| hollow | `Saved` | A version present on disk. Click the name to copy its file path. |
| hollow, dim | `Metadata` | Tracked from a `.civitai.info` sidecar with no weight file next to it. |
| red | `New` | Released after your newest local version. Click the name to open it on Civitai. |
| grey | `Hidden` | A new release you hid. Visible only with `Show hidden` enabled. |
| amber | `Error` | The lookup failed or Civitai refused it (a removed model, one that needs an API key). The reason is printed under the row. |
| dashed | `No match` | Civitai has no release with this file's hash. |

Red is used for one meaning only: a release exists that you do not have.
`New` rows are sorted by release date, newest first.

A `Buzz` badge on a `New` or `Hidden` row means downloading it costs Buzz:

- `Buzz · 5d left` (dashed) is early access. It is free after the date in its
  tooltip, and the badge disappears once that date passes.
- `Buzz · always` (solid) has no free date.

Civitai's public API does not give the price.

`Version` means a specific Civitai release.
`New` uses Civitai release dates: `publishedAt` first, then `createdAt` when `publishedAt` is missing.

A sidecar-only version suppresses that same Civitai version from `New`. It is
shown only when a later version produces an update card. The sidecar must contain
valid `modelId` and version `id` fields; preview PNGs alone and invalid sidecars
are ignored.

## 7. Grouping and sorting

Open `Arrange` in the filter row to set two levels of grouping and the sort
applied inside them.

- `Group` / `Then`: `Nothing`, `Model type`, or `Base model`.
- Default is `Model type` then `Base model`, sorted `Name A–Z`.
- `Furthest behind` sorts by the gap between your newest local version and the
  newest release.
- Base models are grouped by family (`Flux.1 D` and `Flux.2 Klein 9B` both file
  under `Flux`); each row still shows its exact base.
- A card is filed under the base model of the release it is headlining, because
  one Civitai model page can publish on several base models.
- Group headers count the whole result set, not the current page. Click one to
  collapse it; a group continuing past a page break is marked `cont.`

## 8. Mature content

`Settings -> Civitai Updater -> Mature content`:

- `Show everything` (default).
- `Blur previews` blurs the preview image only, so titles stay readable.
- `Hide mature models` removes them from results and reports how many were
  hidden.

## 9. Hidden updates

- Use `Hide` on a remote version row if you do not want to download that version.
- Hidden versions stay hidden across future checks.
- Enable `Show hidden` to review or unarchive them later.
