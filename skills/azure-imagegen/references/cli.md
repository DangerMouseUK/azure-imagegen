# CLI reference (`scripts/image_gen.py`)

Keep `SKILL.md` overview-first. Put verbose command details here.

## What this CLI does

- `generate`: create a new image from a prompt
- `edit`: edit one or more existing images, optionally with a mask
- `generate-batch`: run many prompt jobs from a JSONL file
- `postprocess-transparent`: remove a flat key color with ImageMagick to create a transparent PNG

Real API calls require network access. `--dry-run` does not.

The CLI requires `openai>=1.109.1` for image options and callable Entra token providers.

## Default configuration

- Deployment source: explicit `--deployment` or `AZURE_OPENAI_DEPLOYMENT`
- Size: `1024x1024` for legacy deployments; omitted by default for deployments whose name contains `gpt-image-2`
- Quality: `high`
- Output format: `png`
- Auth mode: `api-key`
- Default env vars:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_DEPLOYMENT`
  - `AZURE_OPENAI_API_KEY`

`AZURE_OPENAI_ENDPOINT` may be either:
- the Azure resource root, for example `https://example.openai.azure.com`
- the full v1 base URL, for example `https://example.openai.azure.com/openai/v1/`

## Config resolution

For endpoint and deployment values, resolve in this order:

1. direct CLI value (`--endpoint`, `--deployment`)
2. custom env-var-name flag (`--endpoint-env`, `--deployment-env`, `--api-key-env`)
3. default env var

If a custom env-var-name flag is set, treat that env var as the source of truth for that setting.

## Quick start

Set a stable path to the skill CLI from the repo root:

```powershell
$IMAGE_GEN = ".\skills\azure-imagegen\scripts\image_gen.py"
```

Install dependencies first with either:

```bash
python -m pip install "openai>=1.109.1" pillow
```

Or:

```bash
uv pip install "openai>=1.109.1" pillow
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
uv run --with "openai>=1.109.1" --with pillow python $IMAGE_GEN generate `
  --prompt "A cozy alpine cabin at dawn" `
  --size 1024x1024 `
  --out ".\output\imagegen\cabin.png"
```

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
uv run --with "openai>=1.109.1" --with pillow --with azure-identity python $IMAGE_GEN generate `
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
uv run --with "openai>=1.109.1" --with pillow python $IMAGE_GEN generate `
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

Edit with high fidelity:

```powershell
python $IMAGE_GEN edit `
  --image ".\portrait.png" `
  --prompt "Change only the shirt to a charcoal wool sweater" `
  --input-fidelity high `
  --quality high `
  --dry-run
```

Create a transparent PNG from a GPT-image-2 key-color result:

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
- `n`
- `size`
- `quality`
- `background`
- `output_format`
- `output_compression`
- `moderation`
- any augmentation field such as `use_case`, `asset_type`, `composition`, or `constraints`

## Notes

- Legacy supported sizes: `1024x1024`, `1536x1024`, `1024x1536`
- GPT-image-2 is inferred from deployment names containing `gpt-image-2`.
- GPT-image-2 supports omitted `--size` for Azure routing, 4K, `1024x1024`, `1536x1024`, `1024x1536`, and custom `WIDTHxHEIGHT` values aligned to multiples of 16.
- GPT-image-2 explicit sizes must be at least 655,360 pixels. Requests over 8,294,400 pixels are allowed with a warning because Azure may resize the final image to fit.
- Microsoft has announced legacy size tiers (`smimage`, `image`, `xlimage`) and token buckets (`16`, `24`, `36`, `48`, `64`, `96`), but this CLI does not expose flags for them until official Image API parameter names are published.
- Transparent backgrounds require `--output-format png` or `webp` and are not supported by GPT-image-2.
- For GPT-image-2 transparent assets, generate on a pure flat key color such as `#00FF00` or `#FF00FF`, then run `postprocess-transparent`.
- `postprocess-transparent` requires ImageMagick `magick` on PATH and PNG output. It is color-based, not semantic segmentation.
- `rembg` can be useful for hair, glass, soft edges, or non-flat backgrounds, but it is not bundled or required.
- `generate-batch` requires `--out-dir`
- `--input-fidelity` is edit-only
- `--moderation` is available only for `generate` and `generate-batch`

## See also

- `references/azure-auth.md`
- `references/prompting.md`
- `references/sample-prompts.md`
- `references/limitations.md`
