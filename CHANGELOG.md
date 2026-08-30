# Changelog

## [1.6.0] - 2026-08-30

### Added
- Two-level grouping for results, set in a new **Arrange** control: group by model type and then by base model (the default, sorted A-Z), by either alone, or not at all. Group headers count what is waiting across the whole result set (`3 models - 4 new`) and collapse to put a type aside.
- Base models are rolled up into families, so `Flux.1 D`, `Flux.2 Klein 9B` and `Flux.2 Klein 9B-base` file under one **Flux** group instead of three; unrecognised values keep their own name rather than being swept into a catch-all. Each row still prints its exact base model.
- **Furthest behind** sort, ordering by the gap between your newest local version and the newest release.
- **Mature content** setting: show everything, blur previews (the image only, so titles stay readable), or hide mature models entirely. Hiding filters server-side and reports how many models were left out instead of quietly shrinking the list.
- Motion for the three moments that carry meaning: results rising in on load, a card settling from provisional to checked with its release dot igniting, and a caret turning on collapse. All of it honours `prefers-reduced-motion`.

### Improved
- Every control shares one height, radius and type ramp; the two action buttons are a matched pair on a grid, and native select chrome was replaced so a dropdown and a filter menu are the same object. The primary button now reads as a pressable object rather than a flat colour fill.
- Red is reserved strictly for releases and the action that finds them - checkboxes and text links are neutral again.
- Paging stays over cards with grouping on, so the rendered list is bounded no matter how large the library grows; a group crossing a page break repeats its header marked `cont.`, the way a ledger section does.

### Fixed
- Collapsing a group no longer makes it disappear with no way back: bands are now drawn from the group outline rather than from the cards, so a folded band keeps its header, its counts and its caret.
- The result list stopped rebuilding itself on every poll tick. A running check refreshes results every 800ms, which tore down and recreated every card and replayed the entry animation, so the panel appeared to flicker constantly. Renders are now skipped entirely when nothing changed, and the entry animation only plays when the page itself changes - a card settling from provisional to checked still announces itself.
- The filter menus showed no dropdown affordance at all: built on `<details>`, they had no caret and read as inert text fields beside real selects. Every dropdown now carries the same chevron (which flips when open), states its label and value in different weights, and the checkbox is drawn instead of left to the platform's white default.
- A stray `display: block` further down the stylesheet was silently cancelling the flex layout on those filter summaries, which is why their contents never aligned.
- The availability badge no longer truncates to `EARLY ACC...` in a narrow row.

## [1.5.0] - 2026-08-28

### Added
- Re-running Check for Updates no longer starts from an empty panel: the previous results are carried over as provisional entries and each card refreshes in place as its model is re-checked — so after downloading a new version, a refresh immediately shows the current state instead of a blank list.
- Missing local previews are backfilled during update checks: sidecars saved while the API was SFW-filtered often contain no image URLs, so the check now pulls the preview from the freshly fetched remote metadata for the installed version and downloads the missing `.preview.png`.
- Video preview conversion falls back to the ffmpeg binary bundled with `imageio-ffmpeg` (now a listed dependency) when ffmpeg is not on PATH, and logs a one-time notice when neither is available.
- Cancelling an update check keeps the carried-over previous results plus everything checked so far, instead of blanking the panel down to the partial run.

### Fixed
- API requests now use `civitai.red/api/v1`: since Civitai's April 2026 domain split, `civitai.com` serves SFW-filtered API responses, so hash lookups and update checks for mature models returned `not_found`. Model page links were already on `civitai.red`.
- Custom embedding paths are no longer silently wiped from the backend config on every settings sync; partial `customPaths` payloads only update the model types they contain, and the frontend now exposes an "Embedding Paths" setting alongside the other model types.
- Video preview thumbnails no longer fail for the large preview videos common on Civitai: the 25MB download cap (which silently aborted 30-60MB videos) was replaced by a fast path that extracts the first frame from the first 12MB, with a full-download fallback capped at 80MB.
- Sidecar files containing valid JSON that is not an object (a list or bare string) are classified as invalid with a warning instead of surfacing raw Python errors in results.
- Reloading the page during a metadata scan reconnects to the running job with progress and Pause/Stop controls (previously only update checks reconnected).
- Grouped result cards no longer mislabel a local video preview as an image when the newest remote version has no preview media.
- The "changes detected" cache pill no longer renders empty "()" details after toggling the sidecar tracking setting.

### Improved
- Redesigned the panel as a "release ledger": flat ink surfaces with hairline seams, IBM Plex Mono for dates/counts/labels, Space Grotesk for names, and a release rail in every card — hollow dot for versions you have, red dot for a new release, dashed ring for metadata-only, gray for hidden. Red now means exactly one thing (a new release on civitai.red); the glassmorphism, hover zooms, and per-type pill colors are gone.
- Result columns adapt to the actual sidebar width via container queries, so version names stay readable in a narrow panel; model names get priority over creator/badges when space runs out.
- Filter dropdowns stay open while toggling options instead of collapsing after every checkbox click.
- Keyboard focus is now visible throughout the panel, and animations respect the reduced-motion system preference.
- Summary lines omit zero-value counts, so the common case reads `2071 checked - 41 updates` instead of padding the line with `0 hidden - 0 errors` and wrapping it in a narrow sidebar.
- Refreshed the README, registry banner, and registry icon to match the panel: the banner and icon are now the release rail itself. The documentation screenshot was regenerated from the new UI and shows only SFW models.
- Version names no longer squeeze the `Hide` button out of view in very narrow rows.
- The backend now refuses to start a second concurrent job (HTTP 409) instead of racing two jobs over the same sidecar files, and the UI surfaces server-provided error messages.
- Finished job records are pruned so long ComfyUI sessions no longer accumulate result sets in memory.
- The last-check inspection runs off the server event loop, so large model libraries no longer stall other ComfyUI requests while it walks the disk.
- Preview downloads close their HTTP streams and clean up temp files reliably on Windows.
- Authentication failures logged from the Civitai API now distinguish a missing API key from an invalid one.
- Added the MIT `LICENSE` file matching the declared package metadata.

## [1.4.1] - 2026-08-05

### Fixed
- Invalidly encoded, binary, or implausibly large `.civitai.info` files are ignored instead of aborting model discovery or consuming excessive memory; UTF-8, UTF-16, and UTF-32 sidecars remain supported.
- Invalid sidecars now produce expandable, non-blocking warnings in the updater UI, including a rename suggestion when a SafeTensors model has the wrong extension.

## [1.4.0] - 2026-07-30

### Added
- Optional sidecar-only model tracking, enabled by default, so valid orphan `.civitai.info` files count as installed Civitai versions.
- Metadata-only labels for update cards and cache-aware detection when tracked sidecars are added, removed, or disabled.
- ComfyUI V3 extension entrypoint while retaining legacy node registration compatibility.
- Availability badges for non-public Civitai model versions.

### Fixed
- Model lookup failures now produce actionable error items instead of appearing as update-free results.
- Metadata-only entries use their stored version IDs and never attempt to hash missing model weights.

### Improved
- Sidecar discovery ignores malformed metadata and avoids duplicate entries when a matching model weight exists.
- Expanded automated coverage for sidecar discovery, refresh behavior, force-rehash handling, grouping, and error reporting.

## [1.3.0] - 2026-05-22

### Removed
- Obsolete "Civitai Domain" settings option from the frontend UI and backend configurations.

### Improved
- Model and version links now always open on `civitai.red` to bypass mature content warnings and redirection prompts.

## [1.2.0] - 2026-05-21

### Added
- Preferred Civitai domain configuration setting (`civitai.com` or `civitai.red` mirror) to dynamically format model page and version links.
- Interactive hover tooltips using custom `.cu-tooltip` styling.
- Tooltip-enabled information triggers (`ⓘ`) next to settings options ("Force rehash", "Refetch existing metadata during scans").

### Fixed
- API key overwrite vulnerability that wiped backend credentials on browser settings hydration.
- Polling resilience in frontend to retry up to 5 times during server restart or network interruption.
- Intercepted 401/403 errors in API client to log clear authentication warnings instead of misleading 404 logs.

### Improved
- Premium UI aesthetics, including glassmorphism layouts, card hovering scale micro-animations, and smooth filter dropdown transitions.
- Renamed buttons "Scan + Check Updates" -> "Check for Updates" and "Scan Only (Metadata)" -> "Scan Metadata Only" for better clarity.
- Styled cache status checks as visual colored pills (`cached` in green, `stale` in orange, `changes detected` in red) with descriptive hover tooltips.
- Aligned user documentation (`README.md` and `wiki/Usage.md`) with the new control panel labels.

## [1.1.0] - 2026-03-04

### Added
- PNG preview sidecar generation for model files.
- Improved scan/check UI flow clarity.

### Fixed
- Correct Comfy Registry `PublisherId` to `gregrichrd`.
- Set explicit MIT license metadata for registry compatibility.

### Improved
- Refreshed docs, disclosure text, screenshot, and publisher metadata.

## [1.0.0] - 2026-02-22

### Added
- Initial ComfyUI release packaging for Civitai Updater.
- Registry-ready icon and banner assets.
- Sidebar custom monochrome icon support.
- README refresh with banner, UI screenshot, and attribution.
