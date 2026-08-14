# quant_distill Upstream API Reference

`quant_distill` is the shared LLM-processing API for upstream source platforms such as
`quant_reddit`, `quant_cnbc`, and `quant_youtube`. Upstream services keep source discovery and
their own persistence. They send text to this API and persist the returned distillation, sentiment,
and entity artifacts in their own stores.

## Base URL

The default local endpoint is `http://localhost:8021`. In Docker Compose, use the service DNS name
and configured port, for example `http://quant-distill:8021`.

All request and response bodies are JSON. There is no inbound authentication in the current API.

## Recommended Integration: `POST /v1/process`

Use this endpoint for normal ingestion. It runs all enabled passes in one request:

1. Distillation of raw text.
2. Sentiment extraction from the distillation.
3. Entity extraction and company-to-ticker resolution.
4. Delivery of extracted sentiment to `quant_sentiment` when configured.
5. Delivery of resolved ticker entities to `quant_signals` when configured.

### Request

```http
POST /v1/process
Content-Type: application/json
```

```json
{
  "source": "quant_youtube",
  "source_type": "youtube",
  "source_item_id": "dQw4w9WgXcQ",
  "title": "Episode title",
  "text": "The complete transcript or source text.",
  "observed_at": "2026-08-14T12:00:00Z",
  "metadata": {
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "channel": "Example Channel"
  },
  "options": {
    "include_sentiment": true,
    "include_entities": true,
    "include_watchlist": true,
    "watchlist_required": false,
    "max_chunk_chars": 12000
  }
}
```

Required fields:

| Field | Type | Notes |
| --- | --- | --- |
| `source` | string | Stable producer name, such as `quant_reddit`, `quant_cnbc`, or `quant_youtube`. |
| `source_type` | string | Source category, such as `reddit`, `cnbc`, or `youtube`. |
| `source_item_id` | string | Stable upstream identifier. It contributes to downstream idempotency keys. |
| `text` | string | Non-empty source content. |

Optional fields:

| Field | Type | Notes |
| --- | --- | --- |
| `title` | string | Source title. It is accepted for context; upstream remains the source of truth. |
| `observed_at` | ISO 8601 timestamp | Timestamp associated with the source item. |
| `metadata` | object | Free-form source metadata. It is passed to downstream delivery APIs. Do not include secrets. |
| `options.include_sentiment` | boolean | Defaults to `true`. |
| `options.include_entities` | boolean | Defaults to `true`. |
| `options.include_watchlist` | boolean | Defaults to `true`; controls Signals delivery for resolved tickers. |
| `options.watchlist_required` | boolean | Defaults to `false`. If true, a Signals delivery failure returns `503`. |
| `options.max_chunk_chars` | integer | Optional override from `1000` through `50000`. Long text is map/reduced. |

### Response

Successful requests return `200`:

```json
{
  "status": "ok",
  "request_id": "f21b213e-2e5f-4c67-82d2-cfcc38149c7c",
  "service": "quant-distill-api",
  "source": {
    "source": "quant_youtube",
    "source_type": "youtube",
    "source_item_id": "dQw4w9WgXcQ",
    "observed_at": "2026-08-14T12:00:00Z"
  },
  "processing": {
    "model": "llama3.1",
    "distill_prompt_version": "v1",
    "sentiment_prompt_version": "v1",
    "entity_prompt_version": "v1",
    "chunk_count": 1,
    "durations_ms": {
      "distill": 810,
      "sentiment": 115,
      "entities": 121,
      "total": 1046
    },
    "token_usage": {
      "prompt_tokens": 2100,
      "completion_tokens": 750,
      "total_tokens": 2850
    },
    "warnings": []
  },
  "distillation": {
    "summary": "**Transcript Summary**\n1. **Topic**: ...",
    "key_topics": ["Topic"],
    "segments": [
      {"speaker": "Host", "role": "host", "summary": "..."}
    ]
  },
  "sentiment": {
    "observations": [
      {
        "subject_type": "ticker",
        "subject": "AAPL",
        "sentiment_label": "bullish",
        "sentiment_score": 0.8,
        "confidence": 0.7,
        "horizon": "5d",
        "reason": "positive guidance"
      }
    ]
  },
  "entities": {
    "items": [
      {
        "raw_mention": "Apple",
        "entity_type": "company",
        "company_name": "Apple Inc.",
        "ticker": "AAPL",
        "speaker": "Host",
        "direction": "long",
        "confidence": 0.8,
        "context": "positive iPhone commentary",
        "watchlist": {
          "entries": [{"signal_id": "signal:AAPL"}]
        }
      }
    ]
  }
}
```

Normalization guarantees:

1. Ticker subjects and entity tickers are uppercased.
2. Sentiment scores are clamped to $[-1, 1]$ and confidence values to $[0, 1]$.
3. Unknown entity types are coerced to `company`; invalid directions are removed.
4. Entities are deduplicated by ticker, or by raw mention when no ticker is resolved.

The response is authoritative for the generated artifacts. Upstream services should persist it using
their own source-item and processing/versioning conventions.

### Downstream Delivery

When downstream API URLs are configured, `/v1/process` also performs delivery:

1. Every sentiment observation is POSTed to `quant_sentiment`.
2. Every resolved ticker entity is POSTed to `quant_signals` if `include_watchlist` is true.
3. Delivery idempotency keys contain the source, source item ID, subject/ticker, model, and prompt version.

This makes repeating the same upstream request safe when the downstream services honor their
idempotency keys. Upstream callers should still persist the returned artifacts; `quant_distill` does
not persist source content or derived content on their behalf.

If optional downstream delivery fails, the request remains successful and the failure is listed in
`processing.warnings`. Set `watchlist_required: true` when the caller must receive `503` for a
Signals delivery failure.

## Focused Endpoints

Use these only when the upstream platform already has an artifact from a prior stage.

### `POST /v1/distill`

Runs distillation only.

```json
{
  "text": "Raw text to distill.",
  "source": "quant_reddit",
  "source_item_id": "t3_abc123",
  "options": {"max_chunk_chars": 12000}
}
```

Returns `distillation` and `processing` metadata. Sentiment, entity extraction, and downstream
delivery are disabled for this endpoint.

### `POST /v1/sentiment`

Extracts sentiment from an existing distillation.

```json
{
  "summary": "Existing distilled summary.",
  "source": "quant_cnbc",
  "source_item_id": "CNBC_20260814_220000_Mad_Money"
}
```

Returns `sentiment` and processing metadata. This endpoint does not deliver observations to
`quant_sentiment`; use `/v1/process` for delivery.

### `POST /v1/entities`

Extracts entities from an existing distillation.

```json
{
  "summary": "Existing distilled summary.",
  "source": "quant_reddit",
  "source_item_id": "t3_abc123",
  "options": {"include_watchlist": true}
}
```

Returns `entities` and processing metadata. This endpoint does not perform sentiment extraction or
call `quant_sentiment`. When `include_watchlist` is true and `quant_signals` is configured,
resolved ticker entities are delivered to `quant_signals`.

## Operational Endpoints

| Method | Path | Use |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe. |
| `GET` | `/ready` | LLM and configured downstream dependency status. Returns `503` only when the LLM is unavailable. |
| `GET` | `/capabilities` | Active model, prompt versions, chunk limit, and delivery availability. |
| `GET` | `/stats` | In-process counters and latency percentiles. |

## Errors and Retries

Errors use this shape:

```json
{
  "status": "error",
  "code": "validation_error",
  "error": "Invalid request",
  "detail": "field 'text' must not be empty"
}
```

| Status | Meaning | Upstream action |
| --- | --- | --- |
| `200` | Request completed. Inspect `processing.warnings` for optional delivery failures. | Persist the returned artifacts. |
| `422` | Invalid JSON body or invalid/missing request field. | Correct the payload; do not retry unchanged. |
| `503` | LLM unavailable, or a required Signals delivery failed. | Retry with exponential backoff. |
| `404` | Unknown route. | Correct the configured API URL/path. |

Use a bounded retry policy for `503` and network failures. Preserve the same `source` and
`source_item_id` on retries to preserve downstream idempotency.

## Minimal Python Client

```python
import httpx

payload = {
    "source": "quant_reddit",
    "source_type": "reddit",
    "source_item_id": "t3_abc123",
    "text": post_text,
    "observed_at": created_at.isoformat(),
    "metadata": {"permalink": permalink, "subreddit": subreddit},
}

response = httpx.post("http://quant-distill:8021/v1/process", json=payload, timeout=180)
response.raise_for_status()
result = response.json()
```
