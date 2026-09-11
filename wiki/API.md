# API

All routes are registered on Comfy's `PromptServer` and return JSON.

## `GET /civitai-updater/config`

Returns:

- `config`: public config (`apiKey` is always empty; `hasApiKey` says whether one is stored)
- `supportedModelTypes`
- `effectiveRoots`: resolved roots per model type (Comfy defaults + `extra_model_paths.yaml` + configured custom paths)

## `POST /civitai-updater/config`

Every field is optional; only the fields present in the request are updated.

- `apiKey`: string
- `cacheTtlMinutes`: integer, 0–10080 (used by the panel to decide when a re-check is suggested)
- `requestTimeoutSeconds`: integer, 5–300
- `maxRetries`: integer, 0–10
- `requestDelayMs`: integer, 0–3000
- `useComfyPaths`, `useExtraModelPaths`, `useCustomPaths`: boolean path-source toggles
- `treatSidecarsAsInstalled`: boolean (defaults to `true`)
- `matureMode`: `show` | `blur` | `hide` (defaults to `show`)
- `customPaths`: object keyed by model type (`checkpoint|lora|vae|unet|embedding`); a value is a list of paths or a string separated by `;` or new lines. Only the keys present in the request are updated.

Response: `config` (public) and `effectiveRoots`, as for `GET`.

## `POST /civitai-updater/jobs/scan`

Starts a metadata scan job (the **Fetch Missing Metadata** button).

Request body:

- `modelTypes`: string array (defaults to all)
- `includeCustomPaths`: boolean (defaults to `true`)
- `refetchMetadata`: boolean
- `forceRehash`: boolean

Response: `jobId`. Returns HTTP 409 with `error` when another job is running.

## `POST /civitai-updater/jobs/check-updates`

Starts an update-check job.

Request body: same as the scan job.

Response: `jobId`, or HTTP 409 as above.

The job is seeded with every item of the previous check so the panel keeps
showing them (marked provisional) while models are re-checked. When the job
finishes, the items of the checked model types are replaced and the items of
any other type are carried over, then the whole set is saved as the new cache.

## `GET /civitai-updater/jobs/active`

Returns `job` (the job record without items) for the running, queued, or
paused job, or `null`.

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
- check: `total`, `resolved`, `withUpdates`, `hiddenUpdates`, `notFound`, `errors`

Both carry `sidecarWarnings`, `modelTypes`, and `includeCustomPaths`.

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

Response fields: `jobId`, `totalItems`, `offset`, `limit`, `mode`, `facets`,
`groups` (the outline with counts for the whole result set), `grouping`,
`startsMidPrimary` / `startsMidSecondary` (whether the page opens inside a
group that began earlier), `matureHidden`, `matureMode`, `items`.

Each item is one model and carries `groupPrimary`, `groupSecondary`,
`groupPrimaryKey`, `groupPathKey`, and:

- `localVersions`
- `newVersions`
- `hiddenNewVersions`
- `isProvisional`

Each local version includes `metadataOnly`, which is `true` when the installed
version is represented only by a valid `.civitai.info` sidecar.

## `GET /civitai-updater/last-check`

Returns `sidecarWarnings` and `data`:

- `null` when no check has been saved; `cacheInvalid: true` is added when the
  saved file is from an older schema
- while a check is running: `jobId`, `checkedAt`, `summary`, `itemCount`, `inProgress: true`
- otherwise the saved check: `jobId` (always `cached`), `checkedAt`, `summary`,
  `itemCount`, `inProgress: false`, `filesChanged`, `filesAdded`, `filesRemoved`

The saved check is loaded as a job with id `cached`, so its items can be paged
through `GET /civitai-updater/jobs/cached/items`.

## `POST /civitai-updater/archived-updates`

Persistently hides one or more remote version IDs for a model.

Request body:

- `modelId`: string
- `versionIds`: string array

Response: `modelId`, `archivedVersionIds`.

## `POST /civitai-updater/archived-updates/restore`

Removes previously hidden remote version IDs for a model. Same body and response.

## `POST /civitai-updater/jobs/{job_id}/pause`

Pauses a running job.

## `POST /civitai-updater/jobs/{job_id}/resume`

Resumes a paused job.

## `POST /civitai-updater/jobs/{job_id}/stop`

Requests cancellation of a running or paused job.
