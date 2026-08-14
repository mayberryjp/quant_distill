# quant_distill

Shared stateless inference worker for distillation, entity extraction, and sentiment extraction.

## Specification

See [docs/SPEC.md](docs/SPEC.md) for the API contract, architecture, and delivery slices.
Upstream platform integrations should use [docs/UPSTREAM_API_REFERENCE.md](docs/UPSTREAM_API_REFERENCE.md).

## Development

```powershell
pip install -e ".[dev]"
pytest
```

## Run Metrics

When `DATABASE_URL` is configured, each completed processing request stores a row in
`quant_distill.run_metrics`. The record includes timestamps, endpoint, source identifiers, model
and prompt versions, duration, input/output character counts, aggregate token usage, and outcome.
Source text and generated summary content are never stored.

Apply the schema before starting the API:

```powershell
docker compose run --rm quant-distill alembic upgrade head
```

Migrations use the `quant_distill` schema and an independent
`quant_distill.quant_distill_alembic_version` table, so this service can share a PostgreSQL
database with other projects that use Alembic.

