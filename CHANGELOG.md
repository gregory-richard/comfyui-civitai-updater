# Changelog

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
