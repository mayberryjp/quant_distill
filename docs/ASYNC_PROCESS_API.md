# quant_distill async `/v1/process` — consumer guide

**Breaking change.** `POST /v1/process` no longer returns the pipeline result. It now
enqueues a job, returns `202 Accepted` immediately, and the caller polls for completion.

Callers that still read the distillation out of the `POST` response will break.

## Why

A full pipeline run takes 2-30 minutes (chunked map/reduce against Ollama, which serialises
requests). Holding an HTTP connection open that long caused client-side read timeouts, and
each in-flight request pinned a waitress thread until the connection limit was hit.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/process` | Enqueue a job. Returns `202` + `job_id` |
| GET | `/v1/jobs/{job_id}` | Poll one job; carries the result when `succeeded` |
| GET | `/v1/jobs` | List/filter jobs |
| GET | `/queue` | Worker and queue depth |

The synchronous `/v1/distill`, `/v1/sentiment` and `/v1/entities` endpoints are unchanged.

## 1. Submit

Request body is unchanged from the old synchronous call:

```http
POST /v1/process
Content-Type: application/json

{
  "source": "quant_cnbc",
  "source_type": "broadcast",
  "source_item_id": "CNBC_20260706_100000_Squawk_Box",
  "title": "Squawk Box",
  "text": "...full transcript...",
  "observed_at": "2026-07-06T10:00:00Z",
  "metadata": {},
  "options": {
    "include_sentiment": true,
    "include_entities": true,
    "include_watchlist": true,
    "watchlist_required": false,
    "max_chunk_chars": null
  }
}
```

`source`, `source_type`, `source_item_id` and a non-empty `text` are required.

Response:

```http
HTTP/1.1 202 Accepted
Location: /v1/jobs/6f1c2d3e-...

{
  "status": "accepted",
  "job_id": "6f1c2d3e-...",
  "job_status": "queued",
  "status_url": "/v1/jobs/6f1c2d3e-..."
}
```

Persist `job_id` against your source item before you start polling. If your process
restarts, you can resume polling instead of resubmitting and paying for the work twice.

Submission errors:

| Status | `code` | Meaning |
|---|---|---|
| 422 | `validation_error` | Malformed body; `detail` names the offending field. Do not retry unchanged |
| 413 | `payload_too_large` | Body over `MAX_REQUEST_BYTES` (16 MiB). Do not retry unchanged |
| 503 | `dependency_unavailable` | Job store unreachable. Retry with backoff |

Because the POST returns immediately, set a short client timeout (5-10s) on it.

## 2. Poll

```http
GET /v1/jobs/6f1c2d3e-...
```

```json
{
  "job_id": "6f1c2d3e-...",
  "endpoint": "/v1/process",
  "status": "succeeded",
  "source": "quant_cnbc",
  "source_item_id": "CNBC_20260706_100000_Squawk_Box",
  "attempts": 1,
  "created_at": "2026-08-16T12:58:05Z",
  "started_at": "2026-08-16T12:58:07Z",
  "completed_at": "2026-08-16T13:26:41Z",
  "error": null,
  "result": { "...": "full ProcessResponse, identical to the old 200 body..." }
}
```

`status` is one of:

| `status` | Meaning | Caller action |
|---|---|---|
| `queued` | Accepted, not started | Keep polling |
| `running` | A worker is processing it | Keep polling |
| `succeeded` | Done; `result` is populated | Consume `result`, stop polling |
| `failed` | Gave up; `error` explains why | Log, stop polling, decide whether to resubmit |

`result` is `null` unless `status` is `succeeded`. When populated it is byte-for-byte the
payload the old synchronous endpoint returned — `source`, `processing`, `distillation`,
`sentiment`, `entities`. No parsing changes are needed downstream of that field.

`404` with `code: "not_found"` means the `job_id` is unknown. Since jobs are persisted in
Postgres, this means a bad id rather than an expired one — jobs are not evicted.

### Recommended polling

- Interval: 15-30s. Jobs run for minutes; polling every second only adds load.
- Timeout: give up after ~60 minutes and alert, rather than polling forever.
- Backoff: on `503`/connection errors, back off and retry — the job keeps running
  server-side regardless of whether you are polling.
- Never resubmit just because polling failed. Resubmitting creates a second job and a
  second set of LLM calls for the same transcript.

```python
job_id = submit(payload)                  # POST /v1/process, short timeout
deadline = time.monotonic() + 3600

while time.monotonic() < deadline:
    job = get_job(job_id)                 # GET /v1/jobs/{job_id}
    if job["status"] == "succeeded":
        return job["result"]
    if job["status"] == "failed":
        raise DistillJobFailed(job["error"])
    time.sleep(20)

raise DistillJobTimeout(job_id)
```

## 3. Failure semantics

A `failed` job carries a short `error` string, e.g.:

```
DependencyUnavailableError: llm distill call failed: ReadTimeout
```

Jobs are **not** retried automatically; `attempts` increments only when a job is claimed by
a worker. One exception: if the service restarts while a job is `running`, that job is
returned to `queued` on boot and picked up again, so `attempts` may reach 2 or more without
you resubmitting.

Resubmitting a failed job is your choice. There is no dedupe on `source_item_id` — submitting
the same item twice produces two jobs and two runs.

## 4. Monitoring

`GET /v1/jobs` supports `status`, `source`, `source_item_id`, `limit`, `offset`, `order`:

```
GET /v1/jobs?status=failed&source=quant_cnbc&limit=20
```

```json
{ "status": "ok", "total": 3, "limit": 20, "offset": 0, "items": [ ... ] }
```

`GET /queue` shows backlog and worker state:

```json
{
  "jobs": { "queued": 12, "running": 1, "succeeded": 340, "failed": 4 },
  "in_flight_total": 1,
  "server": { "queue_depth": 0, "threads_total": 8, "threads_busy": 1 }
}
```

A steadily growing `jobs.queued` means submissions outpace the single worker — expected when
backfilling, since throughput is bounded by Ollama.

`GET /v1/runs` remains the per-run history (durations, token usage, success/failure), keyed
by `request_id` rather than `job_id`.

## 5. Migration checklist

- [ ] Treat `202` as success on submit, not `200`.
- [ ] Read `job_id`/`status_url` from the response and persist it.
- [ ] Drop the long client-side read timeout on the POST.
- [ ] Add a poll loop; move result handling from the POST response to `job["result"]`.
- [ ] Map `failed` jobs onto your existing error path (was: non-2xx from POST).
- [ ] Stop treating a client timeout as "distill failed" — the job is still running.

## 6. Errors

All errors use the standard envelope:

```json
{
  "status": "error",
  "code": "dependency_unavailable",
  "error": "job queue unavailable",
  "detail": "job store is not configured (set DATABASE_URL)"
}
```
