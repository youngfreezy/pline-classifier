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

## Roadmap: decomposed sub-agent pipeline

The current classifier is a single ~150-line prompt doing five jobs at
once: entity lookup, rollup-to-major, exception detection, rule-order
arbitration, and confidence scoring. That's why we needed `gpt-4o`
instead of `gpt-4o-mini` — small models can't juggle that many concerns.

The next iteration breaks the monolith into a pipeline where **only the
hard reasoning is delegated to an LLM**. Decision logic becomes a pure
function over typed pydantic enums, so it's deterministic, free, and
unit-testable. An LLM here would just reintroduce the commitment bias
the decomposition was meant to eliminate.

```
            ┌────────────────────────────────────────────────┐
            │  Track + CID record (joined by ISRC)           │
            └────────────────────┬───────────────────────────┘
                                 │
                                 ▼
        ┌────────────────────────────────────────────────────┐
        │  1. EntityResolver           (pure code, no LLM)   │
        │     - normalize names (lowercase, strip suffixes)  │
        │     - look up each entity in the catalog           │
        │     → EntityTags pydantic                          │
        │       { imprint, owner, label }                    │
        │       each tag ∈ EntityTag enum:                   │
        │         major_frontline | major_distribution |     │
        │         artist_services_exception | middle_tier |  │
        │         indie_distributor | time_varying | unknown │
        └────────────────────┬───────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────────────┐
        │  2. SignalAnalyst       (LLM, small prompt)        │
        │     The ONLY stage that needs an LLM. Reasons over │
        │     fuzzy/unknown entity strings, resolves rollups │
        │     to majors, flags exceptions and time windows.  │
        │     Constrained by SignalSet.model_json_schema()   │
        │     so output enums are guaranteed at decode time. │
        │     → SignalSet pydantic                           │
        │       { imprint_group: MajorGroup|None,            │
        │         owner_group:   MajorGroup|None,            │
        │         exception_flag: awal_like|suspicious_owner │
        │                       |time_varying|None,          │
        │         has_unknown_authoritative: bool,           │
        │         has_corroborating_cid: bool }              │
        └────────────────────┬───────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────────────┐
        │  3. decide_bucket(signals)   (pure function)       │
        │     match/case over SignalSet → Bucket             │
        │     deterministic, free, unit-tested, exhaustive   │
        │                                                    │
        │     def decide_bucket(s: SignalSet) -> Bucket:     │
        │         if s.has_unknown_authoritative:            │
        │             return "unclear"                       │
        │         if s.exception_flag == "suspicious_owner": │
        │             return "unclear"                       │
        │         if s.exception_flag == "awal_like":        │
        │             return "likely_available"              │
        │         if (s.imprint_group and s.owner_group      │
        │             and s.imprint_group==s.owner_group):   │
        │             return "likely_owned"                  │
        │         ...                                        │
        │                                                    │
        │     ← NO LLM here. The work is already done by     │
        │       SignalAnalyst; this is enum lookup, not      │
        │       reasoning. Pydantic + match gives the same   │
        │       guarantees an LLM cannot.                    │
        └────────────────────┬───────────────────────────────┘
                             │
                             ▼
                       Classification
                       (same schema as today)
```

**Why `decide_bucket` is a pure function and not an LLM call**

The original v1 plan had a "BucketDecider" LLM stage here. That was
wrong — pydantic enums + a `match` statement give compile-time
exhaustiveness, deterministic output, zero latency, zero cost, and
trivial unit tests. An LLM at this stage would do nothing the function
can't, while reintroducing the exact commitment-bias failures that the
decomposition was supposed to eliminate. The LLM belongs at the
**signal extraction** boundary (stage 2), not at the decision boundary.

**Why this is a win overall**

- **One LLM call per request**, not three. Same latency as v1,
  dramatically less drift surface.
- **`gpt-4o-mini` becomes viable** for SignalAnalyst — its prompt is
  ~30 lines and its output is constrained to a small enum schema,
  which is exactly what small models are good at.
- **Decision logic is unit-tested**, not eval-tested. `decide_bucket`
  gets a normal pytest suite over every `SignalSet` permutation; only
  the SignalAnalyst stage needs the LLM eval harness.
- **Single-responsibility = debuggable**: an eval miss is either an
  EntityResolver bug (catalog gap) or a SignalAnalyst bug (bad
  reasoning). The blame surface shrinks by two-thirds.
- **Catalog edits don't need LLM re-runs** for the lookup step — only
  for SignalAnalyst's eval, and only if the new entity changes
  reasoning, not just the lookup table.

**Optional 4th stage: SelfCheckAgent**

A second LLM call that re-reads SignalAnalyst's output against the raw
evidence and asks "did the signal extraction look right?" — *not* a
check on `decide_bucket` (which is pure code and doesn't need
checking). Worth adding only if eval shows SignalAnalyst miscategorizing
fuzzy entities. Default: skip it and rely on the eval harness as the
safety net.

## Other next steps

- Promote `data/entities.json` to a Postgres `entities` table once it
  needs non-engineer edits or audit trails
- Promote `data/entities.json` to a Postgres `entities` table once it
  needs non-engineer edits or audit trails
- Add territory-aware ownership for K-pop / Latin / regional cases
  (HYBE, Mavin, Big Machine pre/post acquisition)
- Persist classifications to a `classifications` table keyed by
  `(isrc, model, prompt_version)` for caching + drift tracking
