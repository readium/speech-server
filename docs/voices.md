# Voices

26 voice identities, each declared **once** — not duplicated per language. A voice has one
primary `language` and, optionally, `otherLanguages` it's also capable of speaking. The
identifier has no language segment: it's always `urn:readium:tts:pocket:<name>`, and which
language to speak is chosen at request time via `SynthesizeRequest.language`.

```
urn:readium:tts:pocket:alba    # one identifier for Alba, in any installed language
```

The 26 voice identities, sourced from [kyutai/tts-voices](https://huggingface.co/kyutai/tts-voices):

| Voice | Gender | Origin |
|---|---|---|
| alba | female | Alba MacKenna (CC BY 4.0) |
| anna, vera, fantine, charles, paul, eponine, azelma, george, mary, jane, michael, eve | mixed | VCTK dataset (CC BY 4.0) |
| bill_boerst, peter_yearsley, stuart_bell, caro_davy | mixed | Voice Zero / LibriVox (CC0) |
| marius, javert | male | Voice donations (CC0) |
| cosette | female | Expresso dataset (CC BY-NC 4.0) |
| jean | male | EARS dataset (CC BY-NC 4.0) |
| estelle | female | Unmute production voices |
| giovanni, lola, juergen, rafael | mixed | Kyutai (language reference voices) |

Supported language codes: `en`, `fr`, `it`, `de`, `es`, `pt` — derived directly from PocketTTS model names.

## Cross-language voices

Every voice's `otherLanguages` in `voices.json` documents what it's *capable* of, not whether
it's a *good fit* — an English voice speaking French isn't necessarily natural-sounding. No
ranking or curation of this exists yet; treat it as aspirational, not a quality signal.

**Which cross-language support actually gets installed is controlled by `VOICE_LANGUAGES`**
(see [Configuration](configuration.md)):

| Setting | Behavior |
|---|---|
| _(empty, default)_ | Each voice is only installed for its primary `language`. Smallest download/RAM footprint. |
| `*:*` | Every voice is also installed for its `otherLanguages` — but **only** for languages already in `LANGUAGES`. This never triggers downloading a language model you didn't already select; it just lets already-loaded models serve more voices. |

For exact (voice, language) picks instead of the all-or-nothing `*:*` — e.g. only Alba in French,
or `*:*` minus one voice's Spanish — the same setting takes explicit `voice:lang` pairs
alongside (or instead of) the wildcard; see
[Configuration → per-voice language overrides](configuration.md#per-voice-language-overrides).

`GET /voices` reflects what's actually **installed** on this deployment — its `otherLanguages`
is the installed subset, not the full aspirational list from `voices.json` (see
[API reference](API.md#get-voices)). `GET /service` summarizes each provider's installed
languages without repeating it per voice.

## How it works

PocketTTS pre-computes voice embeddings per voice per language (stored as `.safetensors` files
under `kyutai/pocket-tts-without-voice-cloning`), sized by the target language's model:
~5–8 MB into the 6-layer `en`/`it`/`pt` models, ~24–33 MB into the 24-layer `fr`/`de`/`es`. The embedding is warmed once at
model-load time — no per-request cloning overhead — but only for the (voice, language) pairs
`VOICE_LANGUAGES` and `LANGUAGES` actually call for. Unused language weights can be reclaimed
from the Docker volume with `scripts/prune_weights.py` — see [Configuration → disk space](configuration.md).
