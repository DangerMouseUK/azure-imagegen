---
name: azure-imagegen
description: "Generate, edit, and batch-create images with Azure OpenAI v1 Image API. Use when Codex needs Azure image generation or editing with deployed GPT Image models, including Sunburst and Flare, prompt-to-image, masked edits, transparent backgrounds, product shots, UI mockups, or batch JSONL runs, with API key or Entra ID authentication via the bundled CLI (scripts/image_gen.py)."
---

# Azure ImageGen

Generate or edit images with the bundled `scripts/image_gen.py`. Use the user's Azure deployment name, run a dry run before an unfamiliar configuration, and keep all requests on Azure OpenAI v1 Image API.

## Workflow

1. Select `generate`, `edit`, or `generate-batch`.
2. Collect prompts, exact text, constraints, input images, and masks.
3. Resolve the Azure endpoint/deployment from direct flags, custom environment-variable names, or `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT`.
4. Identify the underlying model. For custom deployment names, use `--image-model` or `AZURE_OPENAI_IMAGE_MODEL`. Do not change the user's deployment to a raw model ID.
5. Run `--dry-run` unless configuration is already known to work.
6. Inspect the result and iterate with one targeted prompt or mask change.

## Command selection

- Input images, retouching, inpainting, localization, background replacement, or "change only X": `edit`.
- Many prompts/assets: `generate-batch`.
- Removing a flat key color from an existing image: `postprocess-transparent`.
- Otherwise: `generate`.

## Model capabilities

| Profile | Size | Quality | Input fidelity |
| --- | --- | --- | --- |
| `gpt-image-1`, `gpt-image-1.5` | 1024x1024, 1536x1024, 1024x1536 | low, medium, high | low/high |
| `gpt-image-1-mini` | Legacy sizes | low, medium, high | Omit |
| `gpt-image-2` | Omitted, auto, custom | low, medium, high | Omit; always high |
| `gpt-image-2.5-sunburst`, `gpt-image-2.5-flare` | Omitted, auto, custom | low, medium, high, xhigh, max, auto | low/high |

Selection: job `image_model` → `--image-model` → `AZURE_OPENAI_IMAGE_MODEL` → inference from the most specific deployment identifier, including snapshots. Explicit `auto` requests inference. Unknown names retain legacy defaults and warn; ask for the underlying model only when it matters to the request.

Sunburst favors editing precision; Flare favors fast everyday generation. Select only a model already available in the user's Azure deployment.

## Defaults and rules

- Preserve `quality=high`, one image, and PNG unless requested otherwise. Higher 2.5 qualities are explicit choices, not automatic upgrades.
- Omit size for Image 2/2.5 unless the user requests a resolution; `--size auto` is also supported. Legacy size defaults to `1024x1024`.
- Custom sizes: 16-pixel alignment, maximum edge 3,840, maximum aspect ratio 3:1, and 655,360–8,294,400 pixels. Image 2.5 above 3,686,400 pixels is experimental.
- Native transparency requires PNG. Image 2 native transparency is preview and depends on Azure availability; use it only when requested. Image 2.5 accepts native transparency.
- If native transparency is unavailable, generate on a pure flat key color and use ImageMagick `postprocess-transparent`. Color removal is not semantic segmentation.
- Azure output is PNG/JPEG; WEBP and compression on PNG fail locally.
- For edits, restate invariants. Use `--input-fidelity high` only for profiles that support it; Image 2 always uses high fidelity and Mini cannot configure it.
- Prefer this CLI over ad hoc wrappers. Keep prompt augmentation short and preserve the user's requirements.
- Existing originals/downscaled copies fail before paid requests unless `--force` is explicit. Batch output paths must be unique even with force.
- Never paste secrets into chat, prompts, source files, or CLI arguments.

## Authentication and dependencies

- Default to `--auth-mode api-key`; read the key from `AZURE_OPENAI_API_KEY` or `--api-key-env`.
- Use `--auth-mode entra` with `DefaultAzureCredential` when configured.
- Python 3.11+, `openai>=3.22.1,<4`, and `pillow>=12.3.0,<13` are required.
- Live Entra calls additionally need `azure-identity>=1.26.0,<2`.
- Prefer installation from the plugin root's `pyproject.toml`; standalone copies can use the equivalent pip/uv recipes.
- ImageMagick `magick` is needed only for local `postprocess-transparent`. No bundled segmentation dependency.

## Runtime scope

Azure `/openai/v1/` Image API only. No classic `api-version` paths, Responses API, streaming, direct OpenAI runtime, or automatic Azure deployment changes. OpenAI retirement dates do not establish Azure retirement dates.

## Reference map

- `references/cli.md`: commands, configuration, batch overrides
- `references/azure-auth.md`: API keys and Entra
- `references/prompting.md`: prompt structure and iteration
- `references/sample-prompts.md`: examples
- `references/limitations.md`: limits, preview caveats, official sources
