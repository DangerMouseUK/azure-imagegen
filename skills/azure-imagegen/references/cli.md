# CLI reference (`scripts/image_gen.py`)

Keep `SKILL.md` overview-first. Put verbose command details here.

## What this CLI does

- `generate`: create a new image from a prompt
- `edit`: edit one or more existing images, optionally with a mask
- `generate-batch`: run many prompt jobs from a JSONL file
- `postprocess-transparent`: remove a flat key color with ImageMagick to create a transparent PNG

Real API calls require network access. `--dry-run` does not.

The CLI requires Python 3.11+, `openai>=3.22.1,<4`, and `pillow>=12.3.0,<13`. Entra live calls additionally require `azure-identity>=1.26.0,<2`.

## Default configuration

- Deployment source: explicit `--deployment` or `AZURE_OPENAI_DEPLOYMENT`
- Model capabilities: `--image-model` or `AZURE_OPENAI_IMAGE_MODEL`, otherwise inferred from the most specific known identifier in the deployment name
- Size: `1024x1024` for legacy profiles; omitted by default for Image 2/2.5 profiles
- Quality: `high`
- Output format: `png`
- Auth mode: `api-key`
- Default env vars:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_DEPLOYMENT`
  - `AZURE_OPENAI_API_KEY`
  - `AZURE_OPENAI_IMAGE_MODEL` (optional)

`AZURE_OPENAI_ENDPOINT` may be either:
- the Azure resource root, for example `https://example.openai.azure.com`
- the full v1 base URL, for example `https://example.openai.azure.com/openai/v1/`

## Config resolution

For endpoint and deployment values, resolve in this order:

1. direct CLI value (`--endpoint`, `--deployment`)
2. custom env-var-name flag (`--endpoint-env`, `--deployment-env`, `--api-key-env`)
3. default env var

If a custom env-var-name flag is set, treat that env var as the source of truth for that setting.

Capability selection resolves JSONL `image_model` → CLI `--image-model` → `AZURE_OPENAI_IMAGE_MODEL` → deployment inference. Values: `auto`, `gpt-image-1`, `gpt-image-1-mini`, `gpt-image-1.5`, `gpt-image-2`, `gpt-image-2.5-sunburst`, `gpt-image-2.5-flare`. Explicit `auto` resumes inference. Unknown deployment names warn and retain legacy capabilities. Snapshot suffixes are recognized; no deployment lookup is performed.

`--deployment` (and JSONL `model`) still selects the actual Azure deployment. The model profile never replaces that request field. Dry-run JSON includes `azure.image_model` and `azure.image_model_source`; these metadata fields are not sent to the SDK.

Dry-run JSON retains `azure.auth_mode` and omits credential values and location details. The former `azure.api_key_source` and `azure.api_key_env_name` fields are no longer emitted. Default and custom credential environment variables are still supported.

## Quick start

Set a stable path to the skill CLI from the repo root:

```powershell
$IMAGE_GEN = ".\skills\azure-imagegen\scripts\image_gen.py"
```

Install dependencies first with either:

```bash
python -m pip install "openai>=3.22.1,<4" "pillow>=12.3.0,<13"
```

Or:

```bash
uv pip install "openai>=3.22.1,<4" "pillow>=12.3.0,<13"
```

Dry-run a generation with default env vars:

```powershell
python $IMAGE_GEN generate --prompt "Minimal ceramic mug on a clean studio background" --dry-run
```

Dry-run with explicit endpoint and deployment:

```powershell
python $IMAGE_GEN generate `
  --endpoint "https://example.openai.azure.com" `
  --deployment "gpt-image-prod" `
  --prompt "Minimal ceramic mug on a clean studio background" `
  --dry-run
```

Live call with API-key auth:

```powershell
uv run --with "openai>=3.22.1,<4" --with "pillow>=12.3.0,<13" python $IMAGE_GEN generate `
  --prompt "A cozy alpine cabin at dawn" `
  --size 1024x1024 `
  --out ".\output\imagegen\cabin.png"
```

### GPT Image 2.5 with a custom deployment name

```powershell
python $IMAGE_GEN generate `
  --deployment "images-prod" `
  --image-model gpt-image-2.5-sunburst `
  --prompt "Product cutout of a travel mug with precise label lettering" `
  --quality xhigh `
  --background transparent `
  --output-format png `
  --size auto `
  --dry-run
```

Keep quality=high unless the user requests higher quality or automatic quality. Flare accepts the same options for faster everyday generation. Native transparency requires PNG; GPT Image 2 transparency prints a preview/Azure availability warning.

GPT-image-2 automatic routing dry-run:

```powershell
python $IMAGE_GEN generate `
  --deployment "gpt-image-2-prod" `
  --prompt "A crisp ecommerce campaign image for a travel mug" `
  --dry-run
```

GPT-image-2 explicit 4K dry-run:

```powershell
python $IMAGE_GEN generate `
  --deployment "gpt-image-2-prod" `
  --prompt "Wide cinematic product image for a homepage hero" `
  --size 3840x2160 `
  --dry-run
```

Live call with Entra auth:

```powershell
uv run --with "openai>=3.22.1,<4" --with "pillow>=12.3.0,<13" --with "azure-identity>=1.26.0,<2" python $IMAGE_GEN generate `
  --auth-mode entra `
  --prompt "A cozy alpine cabin at dawn"
```

If dependencies are already installed in the current Python environment, drop the `uv run ...` prefix and invoke `python $IMAGE_GEN ...` directly.

## Guardrails

- Use `python ...\scripts\image_gen.py` or an equivalent full path.
- Prefer `--dry-run` first when validating config, prompt structure, or output paths.
- Do not pass secrets on the command line.
- Do not add ad hoc wrapper scripts unless the user explicitly asks for one.
- Existing output files, including downscaled copies, are checked before making API calls. Use `--force` to overwrite them.
- Batch output paths must be unique across all jobs and downscaled copies, even with `--force`.

## Common recipes

Generate and also write a downscaled copy for web delivery:

```powershell
uv run --with "openai>=3.22.1,<4" --with "pillow>=12.3.0,<13" python $IMAGE_GEN generate `
  --prompt "A cozy alpine cabin at dawn" `
  --downscale-max-dim 1024 `
  --out ".\output\imagegen\cabin.png"
```

Generate with prompt augmentation fields:

```powershell
python $IMAGE_GEN generate `
  --prompt "A minimal hero image of a ceramic coffee mug" `
  --asset-type "landing page hero" `
  --use-case "stylized-concept" `
  --style "clean product photography" `
  --composition "centered product, generous negative space on the right" `
  --constraints "no logos, no text" `
  --dry-run
```

Generate with custom env-var names:

```powershell
python $IMAGE_GEN generate `
  --endpoint-env "AZURE_OPENNYC_ENDPOINT" `
  --deployment-env "AZURE_OPENNYC_DEPLOYMENT" `
  --api-key-env "AZURE_OPENNYC_API_KEY" `
  --prompt "Editorial product shot of a travel flask" `
  --dry-run
```

Generate many prompts concurrently:

```powershell
python $IMAGE_GEN generate-batch `
  --input ".\tmp\imagegen\prompts.jsonl" `
  --out-dir ".\output\imagegen\batch" `
  --concurrency 5 `
  --dry-run
```

Edit with a mask:

```powershell
python $IMAGE_GEN edit `
  --image ".\input.png" `
  --mask ".\mask.png" `
  --prompt "Replace only the background with a warm sunset gradient" `
  --dry-run
```

Edit with configurable high fidelity (Image 1, 1.5, or 2.5; omit this flag for Image 2/Mini):

```powershell
python $IMAGE_GEN edit `
  --image ".\portrait.png" `
  --prompt "Change only the shirt to a charcoal wool sweater" `
  --input-fidelity high `
  --quality high `
  --dry-run
```

Fallback: create a transparent PNG from an existing key-color result:

```powershell
python $IMAGE_GEN postprocess-transparent `
  --input ".\output\imagegen\product-keyed.png" `
  --out ".\output\imagegen\product-transparent.png" `
  --key-color "#00FF00" `
  --fuzz 6 `
  --trim
```

Preview the ImageMagick command without writing output:

```powershell
python $IMAGE_GEN postprocess-transparent `
  --input ".\output\imagegen\product-keyed.png" `
  --out ".\output\imagegen\product-transparent.png" `
  --key-color "#00FF00" `
  --dry-run
```

## Batch JSONL shape

Each line can be:
- a raw string prompt
- a JSON object with `prompt`
- a JSON object with `prompt` plus per-job overrides

Supported per-job overrides:
- `model`: actual Azure deployment name
- `image_model`: capability profile, or `auto` to infer from that job's deployment
- `out`: output filename
- `n`
- `size`
- `quality`
- `background`
- `output_format`
- `output_compression`
- `moderation`
- any augmentation field such as `use_case`, `asset_type`, `composition`, or `constraints`

Each job is normalized and validated after its overrides, including size defaults. The entire batch is prepared before any live requests, so an invalid later job cannot leave earlier paid requests running. JSON null means no override.

Example mixed deployments:

```jsonl
{"prompt":"A precise product cutout","model":"images-precise","image_model":"gpt-image-2.5-sunburst","quality":"max","background":"transparent","out":"product.png"}
{"prompt":"A quick landscape concept","model":"images-fast","image_model":"gpt-image-2.5-flare","quality":"low","size":"1536x864","out":"concept.png"}
```

## Notes

- Legacy supported sizes: `1024x1024`, `1536x1024`, `1024x1536`
- Capability inference uses the most specific known model identifier, including snapshots. Explicit selection supports custom deployment names.
- Image 2/2.5 support omitted size, `auto`, and custom `WIDTHxHEIGHT` dimensions. Legacy profiles accept only their three fixed sizes.
- Explicit custom sizes must have 16-pixel alignment, maximum edge 3,840, aspect ratio at most 3:1, and 655,360–8,294,400 total pixels. Invalid dimensions fail locally. Image 2.5 above 3,686,400 pixels warns that the resolution is experimental.
- Microsoft has announced legacy size tiers (`smimage`, `image`, `xlimage`) and token buckets (`16`, `24`, `36`, `48`, `64`, `96`), but this CLI does not expose flags for them until official Image API parameter names are published.
- Transparent backgrounds require PNG. Image 2 transparency is preview and opt-in. Image 2.5 supports native transparency. WEBP output is rejected by this Azure CLI.
- If native transparency is unavailable, generate on a pure flat key color such as `#00FF00` or `#FF00FF`, then run `postprocess-transparent`.
- `postprocess-transparent` requires ImageMagick `magick` on PATH and PNG output. It is color-based, not semantic segmentation.
- `rembg` can be useful for hair, glass, soft edges, or non-flat backgrounds, but it is not bundled or required.
- `generate-batch` requires `--out-dir`
- `--output-compression` accepts integers 0–100 and requires JPEG output; `jpg` normalizes to `jpeg`.
- `--input-fidelity` is edit-only, accepts `low` or `high`, and must be omitted for Image 2 (always high) and Mini (unsupported).
- `--moderation` is available only for `generate` and `generate-batch`

## See also

- `references/azure-auth.md`
- `references/prompting.md`
- `references/sample-prompts.md`
- `references/limitations.md`
