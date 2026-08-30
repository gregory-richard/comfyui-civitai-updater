# API

All routes are registered on Comfy's `PromptServer` and return JSON.

## `GET /civitai-updater/config`

Returns:

- public config (API key redacted)
- supported model types
- effective resolved roots (Comfy defaults + `extra_model_paths.yaml` + configured custom paths)

## `POST /civitai-updater/config`

Request body fields:

- `apiKey`: string (optional)
- `requestTimeoutSeconds`: integer (optional)
- `maxRetries`: integer (optional)
- `requestDelayMs`: integer (optional)
- `treatSidecarsAsInstalled`: boolean (optional, defaults to `true`)
- `matureMode`: `show` | `blur` | `hide` (optional, defaults to `show`)
- `customPaths`: object keyed by model type (`checkpoint|lora|vae|unet|embedding`); only the keys present in the request are updated

Response:

- updated public config
- effective resolved roots

## `POST /civitai-updater/jobs/scan`

Starts metadata scan job.

Request body:

- `modelTypes`: string array
- `refetchMetadata`: boolean
- `forceRehash`: boolean

Response:

- `jobId`

## `POST /civitai-updater/jobs/check-updates`

Starts update-check job.

Request body: same as scan job.

Response:

- `jobId`

## `GET /civitai-updater/jobs/{job_id}`

Returns job state:

- `status`: `queued|running|paused|completed|failed|cancelled`
- `progress`, `total`, `message`
- `summary`
- `itemCount`
- `items` (optional compatibility payload; avoid for UI paging path)
- `errors`

Query:

- `includeItems`: `0|1` (default `0`)

Summary shape depends on mode:

- scan: `total`, `refreshed`, `skipped`, `notFound`, `errors`
- check: `total`, `resolved`, `withUpdates`, `notFound`, `errors`

## `GET /civitai-updater/jobs/{job_id}/items`

Query parameters:

- `offset`, `limit`: paging over cards (limit is capped at 500)
- `mode`: `updates` to list only models with a newer release
- `modelType`, `baseModel`: repeatable filters
- `showHidden`: `1` to include releases you hid
- `sort`: `name` | `name-desc` | `type` | `latest-date` | `latest-date-desc` | `behind`
- `groupBy`, `thenBy`: `none` | `type` | `baseFamily` (a value equal to `groupBy` is ignored)
- `collapsed`: repeatable group key, either `Checkpoint` or `Checkpoint||SDXL`
- `mature`: `show` | `blur` | `hide`; omitted falls back to the stored setting

Response adds `groups` (the outline with counts for the whole result set),
`grouping`, `startsMidPrimary` / `startsMidSecondary` (whether the page opens
inside a group that began earlier), `matureHidden` and `matureMode`. Each item
carries `groupPrimary` and `groupSecondary`.

Base response fields: `jobId`, `totalItems`, `offset`, `limit`, `mode`,
`facets`, `items`.

Grouped items now include:

- `localVersions`
- `newVersions`
- `hiddenNewVersions`
- `isProvisional`

Each local version includes `metadataOnly`, which is `true` when the installed
version is represented only by a valid `.civitai.info` sidecar.

## `POST /civitai-updater/archived-updates`

Persistently hides one or more remote version IDs for a model.

Request body:

- `modelId`: string
- `versionIds`: string array

## `POST /civitai-updater/archived-updates/restore`

Removes previously hidden remote version IDs for a model.

## `POST /civitai-updater/jobs/{job_id}/pause`

Pauses a running job.

## `POST /civitai-updater/jobs/{job_id}/resume`

Resumes a paused job.

## `POST /civitai-updater/jobs/{job_id}/stop`

Requests cancellation of a running or paused job.
