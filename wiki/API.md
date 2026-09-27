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
showing them (marked provisional) while models are re-checked. Once the job has
listed the files of the checked types, those seeds are aligned with the disk:
seeds for deleted files are dropped, and new files with a usable
`.civitai.info` get a seed built from it, so a release downloaded since the
last check is not offered as new. When the job finishes, the items of the checked model types are replaced and the items of
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
- `mode`: `updates` to list only models with a newer release, `issues` to list
  only models with a file Civitai could not match (`not_found`) or check
  (`error`); omitted lists every model
- `modelType`, `baseModel`: repeatable filters
- `showHidden`: `1` to include releases you hid
- `sort`: `name` | `name-desc` | `type` | `latest-date` | `latest-date-desc` | `behind`
- `groupBy`, `thenBy`: `none` | `type` | `baseFamily` (a value equal to `groupBy` is ignored)
- `collapsed`: repeatable group key, either `Checkpoint` or `Checkpoint||SDXL`
- `mature`: `show` | `blur` | `hide`; omitted falls back to the stored setting

Response fields: `jobId`, `totalItems`, `offset`, `limit`, `mode`, `facets`,
`groups` (the outline with counts for the whole result set), `grouping`,
`startsMidPrimary` / `startsMidSecondary` (whether the page opens inside a
group that began earlier), `matureHidden`, `matureMode`, `modeCounts`
(`{updates, issues}`: how many models each view lists under the same filters),
`items`.

Each item is one model and carries `groupPrimary`, `groupSecondary`,
`groupPrimaryKey`, `groupPathKey`, and:

- `localVersions`
- `newVersions`
- `hiddenNewVersions`
- `isProvisional`: the card still comes from the previous check's results
  while a check runs
- `issueCount`: how many of its local versions are `error` or `not_found`

Each new or hidden version carries `paid`: `permanent` (downloading costs Buzz,
with no free date), `early` (early access, free from `paidUntil`, which is empty
when Civitai gives no end), or empty. An early-access window that has closed
since the check reads as empty.

Each local version carries the file's check `status` (`ok`, `error`,
`not_found`) and, for `error`, the `error` message. It also includes
`metadataOnly`, which is `true` when the installed
version is represented only by a valid `.civitai.info` sidecar. `modelPath` is
the file the entry was found through (the sidecar, for a metadata-only entry);
`filePath` is always the weights file, where it would be for a metadata-only
entry, with the extension the sidecar names (`.safetensors` when it names none).

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
