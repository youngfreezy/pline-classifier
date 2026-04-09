# P-Line Ownership Classifier

Containerized service that classifies whether a music recording is owned
by a major label group, independently distributed, or genuinely unclear,
based on joined Luminate metadata + YouTube Content ID signals.

Built around an **eval-driven design** loop ([OpenAI cookbook][cookbook]):
the ground-truth set is the spec, the eval harness is the inner loop, and
the prompt + entity catalog are iterated against both a dev set and a
held-out set until both pass 10/10.

[cookbook]: https://cookbook.openai.com/examples/evaluation/getting_started_with_openai_evals

## Architecture

```
                     ┌──────────────────────────────┐
                     │  Client                      │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                ┌───────────────────────────────────────┐
                │  FastAPI  (app/main.py)               │
                │   GET  /tracks                        │
                │   GET  /tracks/{isrc}                 │
                │   POST /tracks/{isrc}/classify        │
                │   POST /classify/batch                │
                └───┬───────────────────────────────┬───┘
                    │                               │
                    ▼                               ▼
        ┌───────────────────────┐       ┌────────────────────────────┐
        │  Repository           │       │  ClassifierService          │
        │  (SQLAlchemy)         │       │  (app/classifier/service.py)│
        │  joins tracks + cid   │       │                             │
        │  on ISRC              │       │  1. fetch joined record     │
        └───────────┬───────────┘       │  2. build evidence          │
                    │                   │  3. call LLM provider with  │
                    ▼                   │     strict JSON schema      │
        ┌───────────────────────┐       │  4. validate via pydantic   │
        │  Postgres 16          │       └────────────┬────────────────┘
        │   tracks              │                    │
        │   youtube_cid (JSONB) │                    ▼
        └───────────────────────┘       ┌────────────────────────────┐
                ▲                       │  LLMProvider (ABC)          │
                │                       │   ├── OpenAIProvider        │
        ┌───────┴───────┐               │   │    structured outputs   │
        │  scripts/     │               │   │    (json_schema strict) │
        │  seed.py      │               │   └── AnthropicProvider     │
        │  (idempotent  │               │        tool-use structured  │
        │   upsert)     │               └────────────┬────────────────┘
        └───────────────┘                            │
                                                     ▼
                                  ┌──────────────────────────────────┐
                                  │  Prompt (app/classifier/prompt.py)│
                                  │   rules + decision order         │
                                  │   ── rendered from ──            │
                                  │  Catalog (app/classifier/catalog) │
                                  │   data/entities.json             │
                                  │    • majors + distribution arms  │
                                  │    • artist-services exceptions  │
                                  │    • middle-tier ambiguous       │
                                  │    • indie distributors          │
                                  │    • time-varying ownership      │
                                  │    • regional majors             │
                                  └──────────────────────────────────┘

                          ──── eval-driven loop ────

        ┌────────────────────────┐         ┌─────────────────────┐
        │  data/ground_truth.    │   ┌────▶│  scripts/eval.py    │
        │  jsonl (dev, 10 rows)  │───┤     │   - hits API        │
        ├────────────────────────┤   │     │   - exact-match     │
        │  data/holdout_eval.    │───┘     │   - RAGAS critic    │
        │  jsonl (holdout, 10)   │         │   - confusion matrix│
        └────────────────────────┘         │   - fail-on-thresh  │
                                            └──────────┬──────────┘
                                                       │
                                                       ▼
                                              prompt + catalog
                                              changes go here ↑
```

## Data model

Two tables joined by ISRC. Kept separate to preserve source provenance —
when CID and Luminate disagree, that *is* the classification problem.

```
tracks                              youtube_cid
  isrc          PK                    isrc          PK / FK → tracks.isrc
  title                               asset_id
  artist                              label
  imprint                             owner
  release_date                        asset_type
                                      artists       JSONB
                                      raw           JSONB  (full payload)
```

## Output buckets

- **`likely_owned`** — major label group (or major-owned distribution arm)
  controls the master. Catalog NOT available to sign.
- **`likely_available`** — independently owned, self-released, or
  released through a pure indie distributor / artist-services entity
  where the artist retains masters. Catalog IS available to sign.
- **`unclear`** — signals conflict, controlling entity is middle-tier
  (does both ownership and distribution), entity is unknown to the
  catalog, or there is insufficient data.

The 4th-bucket case is impossible at decode time: the OpenAI provider
uses **strict JSON-schema structured outputs** generated from a pydantic
`Literal` type, so the model literally cannot emit a token for any
bucket outside the three.

## Catalog-driven prompt

Business logic lives in two places, separated on purpose:

| | Where | What |
|---|---|---|
| **Rules** | [`app/classifier/prompt.py`](app/classifier/prompt.py) | decision order, output schema, bucket definitions, confidence floor |
| **Data** | [`data/entities.json`](data/entities.json) | which labels belong to which major, exceptions, middle-tier, indie distributors, time-varying ownership |

Adding a new label = a one-line JSON edit. The eval harness immediately
re-grades the change end-to-end. The prompt's "GROUND RULE" tells the
model to treat the catalog as the sole source of truth, overriding any
prior knowledge it has about the entities.

## Eval results

Both suites at 10/10 with `gpt-4o`:

| Suite | Rows | Accuracy |
|---|---:|---:|
| `data/ground_truth.jsonl` (dev) | 10 | 10/10 |
| `data/holdout_eval.jsonl` (holdout) | 10 | 10/10 |

The holdout deliberately includes adversarial cases the dev set doesn't
cover: uncorroborated major imprints (no CID), unknown vanity labels,
suspicious owners (artist's own name as `cid.owner`), and distribution
arms not present in the dev set. Each one drove a specific prompt rule.

## Quickstart

```bash
# 1. Drop your OpenAI key (and optionally Anthropic) into .env
echo "OPENAI_API_KEY=sk-..." > .env

# 2. Bring up Postgres + API (auto-seeds from data/*.json)
docker compose up -d --build

# 3. Smoke test
curl localhost:8000/health
curl localhost:8000/tracks/USRC12400001
curl -X POST localhost:8000/tracks/USRC12400001/classify

# 4. Run the eval harness
./venv/bin/python scripts/eval.py                                  # dev set
./venv/bin/python scripts/eval.py --file data/holdout_eval.jsonl   # holdout
./venv/bin/python scripts/eval.py --no-ragas                       # skip RAGAS layer
```

Swagger UI: <http://localhost:8000/docs>

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET`  | `/health` | liveness |
| `GET`  | `/tracks?limit=&offset=&q=` | paginated list, search title/artist/imprint/isrc |
| `GET`  | `/tracks/{isrc}` | joined track + CID (CID may be `null`) |
| `POST` | `/tracks/{isrc}/classify` | classify a single track |
| `POST` | `/classify/batch` | classify many in one request |

## Project layout

```
starter_repo/
├── app/
│   ├── main.py                       # FastAPI app
│   ├── db.py / models.py / config.py
│   ├── repositories.py               # SQL queries (LEFT JOIN tracks + cid)
│   ├── schemas.py                    # pydantic request/response
│   ├── routers/
│   │   ├── tracks.py
│   │   └── classify.py
│   └── classifier/
│       ├── service.py                # ClassifierService + Classification
│       ├── prompt.py                 # rules (rendered from catalog)
│       ├── catalog.py                # loads + renders data/entities.json
│       └── providers/
│           ├── base.py               # LLMProvider ABC
│           ├── openai_provider.py    # strict JSON-schema structured output
│           └── anthropic_provider.py # tool-use structured output
├── scripts/
│   ├── seed.py                       # idempotent upsert from JSON
│   └── eval.py                       # eval harness (deterministic + RAGAS)
├── data/
│   ├── mock_tracks.json
│   ├── mock_youtube_cid.json
│   ├── entities.json                 # the catalog
│   ├── ground_truth.jsonl            # dev eval set
│   └── holdout_eval.jsonl            # held-out eval set
├── docker-compose.yml
└── Dockerfile
```

## Provider flexibility

The `LLMProvider` ABC takes a system prompt, user prompt, and JSON
schema and returns conformant JSON. Both providers enforce the schema
*at decode time* (OpenAI: `response_format=json_schema strict=true`;
Anthropic: forced tool use with `input_schema`), so the bucket field is
guaranteed to be one of the three values regardless of which model
backs the request.

Switch providers via env:

```bash
LLM_PROVIDER=openai     OPENAI_MODEL=gpt-4o
LLM_PROVIDER=anthropic  ANTHROPIC_MODEL=claude-sonnet-4-6
```

## Next steps

- Decompose the monolithic prompt into a pipeline of focused agents
  (entity resolver → signal analyst → bucket decider → self-check) so
  smaller/cheaper models become viable
- Promote `data/entities.json` to a Postgres `entities` table once it
  needs non-engineer edits or audit trails
- Add territory-aware ownership for K-pop / Latin / regional cases
  (HYBE, Mavin, Big Machine pre/post acquisition)
- Persist classifications to a `classifications` table keyed by
  `(isrc, model, prompt_version)` for caching + drift tracking
