#!/usr/bin/env python3
"""Authoring aid: dump your ElevenLabs account's voices so you can curate voices.json.

The Speech Server does NOT mirror ElevenLabs' full catalog — the served list is
operator-configured (a lean, curated voices.json). This script fetches the account's
voices (GET /v2/voices) as a starting point; **trim it down** to the voices you want
served, then save. It prints to stdout by default; pass --write to overwrite
app/data/voices/elevenlabs/voices.json directly (review the diff before committing).

language comes from the voice's accent/language label. otherLanguages is left empty
(the provider serves the whole configured-model language set) unless the API marks the
voice language-restricted (verified_languages) — because language capability is a
property of the MODEL, not the individual voice.

Usage:
    ELEVENLABS_API_KEY=sk_... python scripts/fetch_elevenlabs_voices.py          # print
    ELEVENLABS_API_KEY=sk_... python scripts/fetch_elevenlabs_voices.py --write  # overwrite
    # (key is also read from elevenlabs.env if the env var is unset)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx

_OUT = Path(__file__).parent.parent / "app" / "data" / "voices" / "elevenlabs" / "voices.json"

# ElevenLabs accent label → BCP-47 primary. Fallback en-US.
_ACCENT_TO_BCP47 = {
    "american": "en-US",
    "british": "en-GB",
    "english": "en-GB",
    "australian": "en-AU",
    "irish": "en-IE",
    "transatlantic": "en-US",
    "canadian": "en-CA",
}


def _key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:  # fall back to elevenlabs.env
        env = Path(__file__).parent.parent / "elevenlabs.env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("ELEVENLABS_API_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit("ELEVENLABS_API_KEY not set (env or elevenlabs.env)")
    return key


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _primary(labels: dict[str, str]) -> str:
    lang = (labels.get("language") or "").strip().lower()
    if lang:
        return lang if "-" in lang else lang  # trust an explicit label as-is
    return _ACCENT_TO_BCP47.get((labels.get("accent") or "").strip().lower(), "en-US")


def main() -> None:
    resp = httpx.get(
        "https://api.elevenlabs.io/v2/voices",
        headers={"xi-api-key": _key()},
        params={"page_size": 100},
        timeout=30.0,
    )
    resp.raise_for_status()
    voices = resp.json().get("voices", [])

    entries = []
    id_map: dict[str, str] = {}  # originalName slug → ElevenLabs voice_id (for _VOICE_IDS)
    for v in voices:
        labels = v.get("labels") or {}
        language = _primary(labels)
        primary_prefix = language.split("-")[0].lower()
        # Leave otherLanguages empty → the provider auto-expands to the configured model's set
        # (cross-language). Only emit a restriction when the API marks the voice
        # language-verified (v3 voices carry verified_languages).
        verified = sorted(
            {
                vl["language"].split("-")[0].lower()
                for vl in (v.get("verified_languages") or [])
                if vl.get("language")
            }
            - {primary_prefix}
        )
        other = verified
        # ElevenLabs names are often "George - Warm Storyteller"; take the leading name.
        display = (v.get("name") or v["voice_id"]).split(" - ")[0].strip()
        slug = _slug(display) or v["voice_id"]
        id_map[slug] = v["voice_id"]
        entries.append(
            {
                "name": display,
                "originalName": slug,
                "identifier": f"urn:readium:tts:elevenlabs:{slug}",
                "language": language,
                "otherLanguages": other,
                "gender": (labels.get("gender") or "").strip().lower() or None,
                "quality": "high",
            }
        )

    out = json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
    # voice_ids are mapped in code (_VOICE_IDS in app/providers/elevenlabs.py), NOT in voices.json.
    # Print the map so you can paste entries for the voices you keep.
    id_block = "_VOICE_IDS additions (paste into app/providers/elevenlabs.py):\n" + "".join(
        f'    "{slug}": "{vid}",\n' for slug, vid in id_map.items()
    )
    if "--write" in sys.argv:
        _OUT.write_text(out)
        print(f"Wrote {len(entries)} voices → {_OUT}  (now trim to the ones you want served)")
        print("\n" + id_block, file=sys.stderr)
    else:
        print(out)
        print(f"\n# {len(entries)} voices — curate, then --write to save", file=sys.stderr)
        print("# " + id_block.replace("\n", "\n# "), file=sys.stderr)


if __name__ == "__main__":
    main()
