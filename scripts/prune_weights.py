#!/usr/bin/env python3
"""Prune PocketTTS weight files that don't match the current env config.

By default this reads LANGUAGES + VOICE_LANGUAGES and prunes to the exact install
plan the server would load (reusing plan_install): it drops base language models
for languages no longer enabled AND, within kept languages, individual voice
embeddings no longer used (e.g. a removed cross-language pair). What's still needed
stays; anything re-added later re-downloads from the HF cache on next start.

PocketTTS caches everything — base model, tokenizer, and per-voice embeddings —
under `languages/<lang>/` inside two HuggingFace repos (`kyutai/pocket-tts` and
`kyutai/pocket-tts-without-voice-cloning`), sharing one snapshot revision per
repo (confirmed by reading pocket_tts's own config/*.yaml and utils/utils.py —
every language config references the same two revision hashes). That makes
per-language pruning safe: each language's files live under one exclusive path
prefix, distinct from every other language's.

Content-addressed HF cache layout means each snapshot file is a symlink into
`blobs/<sha256>`. Before deleting a blob, this script confirms no OTHER
surviving symlink (outside the languages being pruned) points to the same
blob — belt-and-braces, since these files shouldn't collide in practice, but a
wrong deletion here corrupts a live model.

Default is a dry-run report. Pass --apply to actually delete.

Usage (inside the container, where HF_HOME=/weights is mounted):
    python scripts/prune_weights.py                 # report only (env config)
    python scripts/prune_weights.py --apply          # actually delete
    python scripts/prune_weights.py --keep en,fr --apply   # language-level override,
                                                           # keeps all embeddings
Or via make (from the host): `make prune-models` / `make prune-models-apply`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPOS = ["kyutai/pocket-tts", "kyutai/pocket-tts-without-voice-cloning"]


def _repo_cache_dir(hub_dir: Path, repo_id: str) -> Path:
    # HF cache naming: "org/name" -> "models--org--name"
    return hub_dir / ("models--" + repo_id.replace("/", "--"))


def _lang_folder_map() -> dict[str, str]:
    """BCP-47 prefix -> PocketTTS language folder name. Reuses the app's own
    mapping so this script can't silently drift from what the provider loads."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.providers.pocket_tts import _LANG_MODEL  # noqa: PLC0415

    return dict(_LANG_MODEL)


def _dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def _resolve_blob(symlink: Path) -> Path | None:
    try:
        target = symlink.resolve()
    except OSError:
        return None
    return target if target.is_file() else None


def _blob_has_other_references(
    blob: Path, snapshots_dir: Path, exclude_prefixes: list[Path]
) -> bool:
    """True if any symlink under snapshots_dir, outside exclude_prefixes,
    resolves to the same blob."""
    for f in snapshots_dir.rglob("*"):
        if not f.is_symlink():
            continue
        if any(str(f).startswith(str(p)) for p in exclude_prefixes):
            continue
        if _resolve_blob(f) == blob:
            return True
    return False


def _install_plan_from_env() -> tuple[set[str], set[tuple[str, str]]]:
    """What to KEEP per the current env config (LANGUAGES + VOICE_LANGUAGES),
    exactly matching what the server loads. Returns (language folder names,
    {(folder, voice_originalName)} embeddings). Reuses plan_install so it can't
    drift; empty VOICE_LANGUAGES = default = native voices only, handled naturally."""
    import json  # noqa: PLC0415

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.config.settings import settings  # noqa: PLC0415
    from app.providers.pocket_tts import _LANG_MODEL, _VOICES_PATH  # noqa: PLC0415
    from app.providers.voice_loading import VoiceEntry, plan_install  # noqa: PLC0415

    enabled = frozenset(settings.language_list) & frozenset(_LANG_MODEL)
    install_all = settings.voice_install_all
    add = settings.voice_language_add_map
    remove = settings.voice_language_remove_map
    entries = [VoiceEntry.model_validate(v) for v in json.loads(_VOICES_PATH.read_text())]

    keep_folders: set[str] = set()
    keep_emb: set[tuple[str, str]] = set()
    for e in entries:
        key = e.originalName.lower()
        plan = plan_install(
            e, enabled, install_all, add.get(key, frozenset()), remove.get(key, frozenset())
        )
        if plan is None:
            continue
        _, installed = plan
        for lang in installed:
            folder = _LANG_MODEL[lang]
            keep_folders.add(folder)
            keep_emb.add((folder, e.originalName))
    return keep_folders, keep_emb


def _delete_file_blob_safe(f: Path, snapshots_dir: Path) -> None:
    """Delete a snapshot symlink and its blob, unless another symlink still uses it."""
    if f.is_symlink():
        blob = _resolve_blob(f)
        if blob is not None and not _blob_has_other_references(blob, snapshots_dir, [f]):
            blob.unlink(missing_ok=True)
    f.unlink(missing_ok=True)


def _prune_embeddings(
    lang_dir: Path, keep_emb: set[tuple[str, str]], snapshots_dir: Path, apply: bool
) -> int:
    """Within a KEPT language dir, delete voice embeddings not in the install plan.
    Returns bytes freed. Base model / tokenizer are never touched here."""
    folder = lang_dir.name
    emb_dir = lang_dir / "embeddings"
    if not emb_dir.is_dir():
        return 0
    freed = 0
    for emb in sorted(emb_dir.glob("*.safetensors")):
        if (folder, emb.stem) in keep_emb:
            continue
        try:
            fsize = emb.resolve().stat().st_size
        except OSError:
            fsize = 0
        act = "DELETE" if apply else "would-delete"
        print(f"  {act:12s} {folder:12s} embeddings/{emb.stem} {fsize / 1e6:7.2f} MB")
        freed += fsize
        if apply:
            _delete_file_blob_safe(emb, snapshots_dir)
    return freed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually delete (default: dry-run report only)"
    )
    parser.add_argument(
        "--keep",
        default=None,
        help="Comma-separated BCP-47 prefixes to keep (default: LANGUAGES env var)",
    )
    args = parser.parse_args()

    hf_home = Path(os.environ.get("HF_HOME", "/weights"))
    hub_dir = hf_home / "hub"
    if not hub_dir.is_dir():
        print(f"No HF cache found at {hub_dir} — nothing to prune.")
        return 0

    # --keep overrides to a language-level prune (keeps every embedding in kept
    # languages). Default reads the full env config and prunes to the exact install
    # plan — base models AND per-voice embeddings — matching what the server loads.
    keep_emb: set[tuple[str, str]] | None
    if args.keep is not None:
        lang_map = _lang_folder_map()
        keep = {v.strip().lower() for v in args.keep.split(",") if v.strip()} or {"en"}
        keep_folders = {lang_map[p] for p in keep if p in lang_map}
        keep_emb = None
        unknown = keep - set(lang_map)
        if unknown:
            print(f"Warning: unsupported prefixes in --keep, ignored: {sorted(unknown)}")
        print(f"HF cache: {hub_dir}")
        print(f"Keeping languages (--keep): {sorted(keep)} -> folders {sorted(keep_folders)}")
    else:
        keep_folders, keep_emb = _install_plan_from_env()
        print(f"HF cache: {hub_dir}")
        print(
            f"Keeping per env config: {len(keep_folders)} language(s), "
            f"{len(keep_emb)} voice embedding(s)"
        )
        print(f"  languages: {sorted(keep_folders)}")
    print()

    total_freed = 0
    total_kept = 0
    any_found = False

    for repo_id in _REPOS:
        repo_dir = _repo_cache_dir(hub_dir, repo_id)
        snapshots_dir = repo_dir / "snapshots"
        if not snapshots_dir.is_dir():
            continue

        for snapshot in snapshots_dir.iterdir():
            langs_dir = snapshot / "languages"
            if not langs_dir.is_dir():
                continue

            for lang_dir in sorted(langs_dir.iterdir()):
                if not lang_dir.is_dir():
                    continue
                any_found = True
                size = _dir_size(lang_dir)

                where = f"{repo_id:42s} languages/{lang_dir.name:15s}"
                if lang_dir.name in keep_folders:
                    # Kept language — prune only its unused voice embeddings (env mode).
                    freed = (
                        _prune_embeddings(lang_dir, keep_emb, snapshots_dir, args.apply)
                        if keep_emb is not None
                        else 0
                    )
                    kept_size = size - freed
                    total_freed += freed
                    total_kept += kept_size
                    suffix = f" (pruned {freed / 1e6:.1f} MB embeddings)" if freed else ""
                    print(f"  KEEP    {where} {kept_size / 1e6:8.1f} MB{suffix}")
                    continue

                action = "DELETE" if args.apply else "would-delete"
                print(f"  {action:12s} {where} {size / 1e6:8.1f} MB")
                total_freed += size

                if not args.apply:
                    continue

                # Delete blobs first (while we can still resolve the symlinks),
                # skipping any blob still referenced from outside this language dir.
                exclude = [lang_dir]
                for f in lang_dir.rglob("*"):
                    if not f.is_symlink():
                        continue
                    blob = _resolve_blob(f)
                    if blob is None:
                        continue
                    if _blob_has_other_references(blob, snapshots_dir, exclude):
                        continue
                    blob.unlink(missing_ok=True)

                import shutil  # noqa: PLC0415

                shutil.rmtree(lang_dir, ignore_errors=True)

    print()
    if not any_found:
        print("No per-language weight directories found — nothing to prune.")
        return 0

    verb = "Freed" if args.apply else "Would free"
    print(f"{verb}: {total_freed / 1e6:.1f} MB   Kept: {total_kept / 1e6:.1f} MB")
    if not args.apply:
        print("Dry run — re-run with --apply to actually delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
