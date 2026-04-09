# P-Line Ownership Classifier

## Context

A **P-line** (production line) identifies who owns a sound recording. A music company evaluating whether to sign or work with an artist needs to know: is this catalog owned by a major label, independently distributed, or somewhere in between?

You have mock data from two sources representing real music industry data. Your interviewer will guide you through what to build.

## Data Files

| File | Description |
|------|-------------|
| `data/mock_youtube_cid.json` | YouTube Content ID data keyed by ISRC. Each entry contains metadata (`label`, `artist`) and ownership (`owner`) fields. `null` means no CID match. |
| `data/mock_tracks.json` | Track metadata array — ISRC, title, artist, imprint (label name from Luminate), release date. |

## Ownership Signals

The music industry has three major label groups — Universal Music Group (UMG), Sony Music, and Warner Music Group. Each owns many sub-labels and distribution arms. There are also independent distributors that allow artists to self-release, and some entities that operate in between.

Your system should determine whether a track is owned by a major label, independently distributed, or unclear based on the signals in the data. The ground truth examples will help you understand the patterns.

## How You'll Be Evaluated

- **Generalization** — We will test your system against data beyond what's in the provided samples. Build for robustness, not just the golden dataset.
- **Software design** — API structure, code organization, and how easy it would be for another engineer to pick this up.
- **Model flexibility** — Your implementation should not be locked to a single LLM provider.

## Notes

- You need your own LLM API key (OpenAI or Anthropic)
- AI assistants are encouraged — use whatever tools you normally use
- This is a pair programming session — think out loud, ask questions, let's build together
