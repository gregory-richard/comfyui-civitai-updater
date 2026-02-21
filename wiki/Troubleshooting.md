# Troubleshooting

## Sidebar tab not visible

1. Confirm repo is under Comfy `custom_nodes`.
2. Confirm restart was a full process restart.
3. Check terminal logs for `Civitai updater: routes registered`.
4. Check browser console for JS import/runtime errors.

## Deprecation warnings in startup log

Warnings such as:

- `Detected import of deprecated legacy API: /scripts/ui.js`

usually originate from other custom nodes using old APIs. They are not automatically an updater failure.

## No models found

1. Verify selected model types.
2. Verify effective root counts shown in the updater tab and expand `Show paths`.
3. Check path source toggles in `Settings -> Civitai Updater`.
4. Add custom paths in `Settings -> Civitai Updater`.
5. Re-run scan/check.

## Frequent `not_found` rows

This means Civitai has no hash match for those local files. Typical reasons:

- converted/pruned/repacked files
- unpublished/private resources
- legacy models missing hash records on Civitai

## API key issues

If gated resources fail:

1. Set API key in updater settings.
2. Save in `Settings -> Civitai Updater`.
3. Re-run check.
