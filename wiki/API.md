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
- `customPaths`: object keyed by model type (`checkpoint|lora|vae|unet`)

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

Returns paged job items.

Query params:

- `offset`: integer, default `0`
- `limit`: integer, default `25`
- `mode`: optional, supports `updates`

Response fields:

- `jobId`
- `totalItems`
- `offset`
- `limit`
- `mode`
- `items`

## `POST /civitai-updater/jobs/{job_id}/pause`

Pauses a running job.

## `POST /civitai-updater/jobs/{job_id}/resume`

Resumes a paused job.

## `POST /civitai-updater/jobs/{job_id}/stop`

Requests cancellation of a running or paused job.
