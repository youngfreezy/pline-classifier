"""Loads the entity catalog and renders it into prompt sections.

Keeping this separate from prompt.py means the *rules* (how to weigh
sources, decision order, output schema) stay in the prompt while the
*data* (which labels belong to which group) lives in data/entities.json.
Adding a new label is a one-line JSON edit, not a prompt rewrite.

Promotion path: when this catalog needs non-engineer edits or audit
trails, lift it into a Postgres `entities` table with the same shape and
have catalog.load() pull from the DB instead. The render_* functions
don't need to change.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "entities.json"


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(CATALOG_PATH.read_text())


def render_majors_section(catalog: dict) -> str:
    lines = []
    for code, group in catalog["majors"].items():
        lines.append(f"## {group['display_name']} ({code}) — major-owned")
        lines.append("Frontline labels: " + ", ".join(group["frontline_labels"]))
        lines.append("Distribution arms: " + ", ".join(group["distribution_arms"]))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_exceptions_section(catalog: dict) -> str:
    lines = []
    for e in catalog["artist_services_exceptions"]:
        aliases = f" (aka {', '.join(e['aliases'])})" if e["aliases"] else ""
        parent = f" — owned by {e['parent']}" if e["parent"] else ""
        lines.append(f"- **{e['name']}**{aliases}{parent}: {e['note']}")
    return "\n".join(lines)


def render_middle_tier_section(catalog: dict) -> str:
    lines = []
    for e in catalog["middle_tier"]:
        aliases = f" (aka {', '.join(e['aliases'])})" if e["aliases"] else ""
        lines.append(f"- **{e['name']}**{aliases}: {e['note']}")
    return "\n".join(lines)


def render_indie_section(catalog: dict) -> str:
    return ", ".join(catalog["indie_distributors"])


def render_time_varying_section(catalog: dict) -> str:
    lines = []
    for e in catalog["time_varying"]:
        lines.append(f"- **{e['name']}**: {e['note']}")
        for h in e["history"]:
            window = (
                f"until {h['until']}" if "until" in h else f"from {h['from']}"
            )
            owner = f" (owner: {h['owner']})" if "owner" in h else ""
            lines.append(f"    - {window}: {h['status']}{owner}")
    return "\n".join(lines)


def render_regional_section(catalog: dict) -> str:
    lines = []
    for e in catalog["regional_majors"]:
        lines.append(f"- **{e['name']}** ({e['scope']}): {e['note']}")
    return "\n".join(lines)
