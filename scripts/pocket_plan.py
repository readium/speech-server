#!/usr/bin/env python3
"""Print what the current env config (LANGUAGES + VOICE_LANGUAGES) installs.

A plain "what will be installed" view for the wizard: the coverage mode
(default / all / custom), native voices per language, and how many cross-language
pairs are added on top. Sizes/RAM live in docs/configuration.md, not here — the
wizard stays readable.

Reuses app.providers.voice_loading.plan_install so the picture can't drift from
what the server actually loads.

Usage:  pocket_plan.py <voices.json> <LANGUAGES> <VOICE_LANGUAGES>
        pocket_plan.py --selftest
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.providers.voice_loading import VoiceEntry, plan_install  # noqa: E402

SUPPORTED = ("en", "fr", "it", "de", "es", "pt")


def _split(csv: str) -> list[str]:
    return [p.strip().lower() for p in csv.split(",") if p.strip()]


# ponytail: mirrors Settings._parse_voice_language_overrides / voice_install_all
# (settings.py) — that's the source of truth; keep this tokenizer in sync if the
# VOICE_LANGUAGES grammar changes. Kept separate to avoid constructing Settings().
def _parse_voice_languages(
    raw: str,
) -> tuple[bool, dict[str, set[str]], dict[str, set[str]]]:
    wildcard = False
    add: dict[str, set[str]] = {}
    remove: dict[str, set[str]] = {}
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok == "*:*":
            wildcard = True
            continue
        target = add
        if tok.startswith("-"):
            target, tok = remove, tok[1:]
        if ":" not in tok:
            continue
        voice, lang = tok.split(":", 1)
        voice, lang = voice.strip().lower(), lang.strip().lower()
        if voice and lang:
            target.setdefault(voice, set()).add(lang)
    return wildcard, add, remove


def plan(voices_path: str, langs_csv: str, voice_languages: str) -> dict[str, Any]:
    entries = [VoiceEntry.model_validate(v) for v in json.loads(Path(voices_path).read_text())]
    enabled = frozenset(_split(langs_csv)) & frozenset(SUPPORTED)
    wildcard, add, remove = _parse_voice_languages(voice_languages)

    installed = 0
    cross_pairs = 0
    natives: dict[str, list[str]] = {lang: [] for lang in enabled}
    for e in entries:
        key = e.originalName.lower()
        result = plan_install(
            e, enabled, wildcard,
            frozenset(add.get(key, set())), frozenset(remove.get(key, set())),
        )
        if result is None:
            continue
        _, langs = result
        installed += 1
        primary = e.language.split("-")[0].lower()
        cross_pairs += len(langs - {primary})
        if primary in natives:
            natives[primary].append(e.originalName)

    if wildcard:
        mode = "all"
    elif add or remove:
        mode = "custom"
    else:
        mode = "default"

    return {
        "mode": mode,
        "languages": sorted(enabled),
        "installed_voices": installed,
        "cross_pairs": cross_pairs,
        "natives": natives,
    }


_MODE_BLURB = {
    "default": "native voices of your selected languages only",
    "all": "every voice also speaks every other selected language",
    "custom": "native voices + your hand-picked cross-language pairs",
}


def render(p: dict[str, Any]) -> str:
    lines = [
        f"  Languages:        {', '.join(p['languages']) or '(none)'}",
        f"  Coverage:         {p['mode']} — {_MODE_BLURB[p['mode']]}",
        f"  Voices installed: {p['installed_voices']}",
    ]
    if p["cross_pairs"]:
        lines.append(f"  Cross-language:   {p['cross_pairs']} pair(s) added on top of defaults")
    lines.append("  Native voices per language:")
    for lang in p["languages"]:
        names = p["natives"][lang]
        if not names:
            shown = "(none)"
        elif len(names) <= 3:
            shown = ", ".join(names)
        else:
            shown = f"{names[0]} (+{len(names) - 1} more)"
        lines.append(f"      {lang}: {shown}")
    return "\n".join(lines)


def _selftest() -> None:
    root = Path(__file__).parent.parent
    vj = str(root / "app" / "data" / "voices" / "pocket" / "voices.json")

    d = plan(vj, "en", "")
    assert d["mode"] == "default" and d["installed_voices"] == 21 and d["cross_pairs"] == 0, d

    d = plan(vj, "en,fr", "")
    assert d["installed_voices"] == 22 and d["cross_pairs"] == 0, d

    # all + en,fr: every voice that can speak a selected language installs — incl.
    # non-native-primary ones (giovanni/lola/... speaking fr/en cross-language).
    a = plan(vj, "en,fr", "*:*")
    assert a["mode"] == "all" and a["installed_voices"] == 26 and a["cross_pairs"] == 28, a

    c = plan(vj, "en,fr", "alba:fr")
    assert c["mode"] == "custom" and c["cross_pairs"] == 1, c
    print("pocket_plan selftest OK")


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        _selftest()
        return 0
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    voices_path, langs, voice_languages = sys.argv[1:4]
    print(render(plan(voices_path, langs, voice_languages)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
