# Voices

156 voices across 7 language variants (26 voice identities × 6 languages). Every voice is available in every language — `alba` speaking English, `alba` speaking French, `alba` speaking German, etc. Only languages listed in `LANGUAGES` are loaded at startup (~240 MB RAM per language per worker).

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

## Voice URIs

Voice URIs are language-scoped — the same speaker in different languages gets a distinct URI:

```
urn:readium:tts:pocket:en-alba    # Alba speaking English
urn:readium:tts:pocket:fr-alba    # Alba speaking French
urn:readium:tts:pocket:de-alba    # Alba speaking German
```

Supported language codes: `en`, `fr`, `it`, `de`, `es`, `pt` — derived directly from PocketTTS model names.

## How it works

PocketTTS pre-computes voice embeddings for every voice × language combination (stored as `.safetensors` files in `kyutai/pocket-tts-without-voice-cloning`). The voice sample is encoded once at model-load time — no per-request cloning overhead.
