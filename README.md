# Azure ImageGen Plugin

`azure-imagegen` is a Codex plugin that packages an Azure-first image generation skill plus a bundled Python CLI for Azure OpenAI v1 image workflows.

The installable unit is the repository root. The existing skill at [`skills/azure-imagegen`](./skills/azure-imagegen) remains usable for direct skill installs during transition, but plugin installation is now the primary path.

## What it includes

- plugin manifest at [`.codex-plugin/plugin.json`](./.codex-plugin/plugin.json)
- Codex skill at [`skills/azure-imagegen`](./skills/azure-imagegen)
- bundled CLI at [`skills/azure-imagegen/scripts/image_gen.py`](./skills/azure-imagegen/scripts/image_gen.py)
- plugin UI assets under [`assets/`](./assets)
- validation tests and CI smoke checks

## Scope

- Azure OpenAI v1 only
- Image API workflows only
- `generate`, `edit`, and `generate-batch`
- API key or Entra ID authentication

## Install As A Plugin

Preferred home-local install:

```powershell
git clone https://github.com/dangermouseuk/azure-imagegen.git "$HOME\plugins\azure-imagegen"
```

Preferred repo-local install inside a project that should use the plugin:

```powershell
git clone https://github.com/dangermouseuk/azure-imagegen.git ".\plugins\azure-imagegen"
```

This repository does not commit a marketplace catalog because it is a single plugin. Register it in your local marketplace instead.

Home-local marketplace file: `~/.agents/plugins/marketplace.json`

```json
{
  "name": "local-plugins",
  "interface": {
    "displayName": "Local Plugins"
  },
  "plugins": [
    {
      "name": "azure-imagegen",
      "source": {
        "source": "local",
        "path": "./plugins/azure-imagegen"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

Repo-local marketplace file: `.agents/plugins/marketplace.json`

```json
{
  "name": "project-plugins",
  "interface": {
    "displayName": "Project Plugins"
  },
  "plugins": [
    {
      "name": "azure-imagegen",
      "source": {
        "source": "local",
        "path": "./plugins/azure-imagegen"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

After registration, Codex can discover the plugin and the bundled skill will still trigger as `$azure-imagegen`.

## Legacy Skill-Only Install

If you only want the skill and not the plugin packaging, copy [`skills/azure-imagegen`](./skills/azure-imagegen) into one of these locations:

- `~/.codex/skills/azure-imagegen`
- `.agents/skills/azure-imagegen`

Example:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null
Copy-Item -Recurse ".\skills\azure-imagegen" "$HOME\.codex\skills\azure-imagegen"
```

## Dependency Setup

Python 3.11 is the CI baseline.

Install runtime dependencies from the plugin root:

```bash
python -m pip install -e .
```

Add optional Entra authentication support:

```bash
python -m pip install -e ".[entra]"
```

Install development dependencies for validation and tests:

```bash
python -m pip install -e ".[dev,entra]"
```

If you use `uv`, the equivalent workflow is:

```bash
uv sync --extra dev --extra entra
```

The runtime dependency set is:

- `openai>=1.109.1`
- `pillow`
- optional `azure-identity` for live Entra-authenticated runs
- optional ImageMagick `magick` CLI for local transparent-background post-processing

## Quick Start

From the plugin root:

```powershell
python .\skills\azure-imagegen\scripts\image_gen.py generate `
  --endpoint "https://example.openai.azure.com" `
  --deployment "gpt-image-prod" `
  --prompt "Minimal ceramic mug on a clean studio background" `
  --dry-run
```

That performs a zero-network configuration smoke test. For live calls, use your Azure endpoint and deployment or set:

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT
AZURE_OPENAI_API_KEY
```

For deeper CLI usage and prompt recipes, use the bundled skill references instead of this README:

- [CLI reference](./skills/azure-imagegen/references/cli.md)
- [Azure auth reference](./skills/azure-imagegen/references/azure-auth.md)
- [Prompting guidance](./skills/azure-imagegen/references/prompting.md)
- [Sample prompts](./skills/azure-imagegen/references/sample-prompts.md)

## GPT-image-2

This plugin supports Microsoft Foundry GPT-image-2 deployments through the same Azure OpenAI v1 Image API path. The CLI infers GPT-image-2 behavior when the deployment name contains `gpt-image-2`.

- Omit `--size` for GPT-image-2 to let Azure's routing layer select the generation configuration.
- Pass explicit sizes such as `3840x2160`, `2160x3840`, `1024x1024`, `1536x1024`, `1024x1536`, or another `WIDTHxHEIGHT` value with both dimensions aligned to multiples of 16.
- Explicit GPT-image-2 sizes must be at least 655,360 pixels. Requests over 8,294,400 pixels are allowed with a warning because Azure may resize the final output.
- The Microsoft announcement names legacy size tiers and token buckets, but this plugin does not expose guessed flags for them until Microsoft publishes official Image API parameter names.
- GPT-image-2 does not support native `background=transparent`. Generate on a flat key color such as `#00FF00` and run `postprocess-transparent` with ImageMagick, or use a GPT-image-1/1.5 deployment for native transparent PNG output.

Example GPT-image-2 cutout post-process:

```powershell
python .\skills\azure-imagegen\scripts\image_gen.py postprocess-transparent `
  --input ".\output\imagegen\product-keyed.png" `
  --out ".\output\imagegen\product-transparent.png" `
  --key-color "#00FF00" `
  --fuzz 6 `
  --trim
```

## Compatibility And Limitations

- Azure-only: no direct non-Azure OpenAI endpoint support
- v1-only: no classic `api-version` Azure endpoint mode
- Image API only: no Responses API runtime path in this version
- local Python environment required for the bundled CLI

See [limitations](./skills/azure-imagegen/references/limitations.md) for the explicit boundary list.

## Validation And Release

Local validation:

```bash
python -m pip install -e ".[dev,entra]"
pytest
```

If you have the Codex `skill-creator` tooling installed locally, you can also run:

```bash
python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/azure-imagegen
```

GitHub Actions runs packaging validation and dry-run smoke tests on pull requests, pushes to `main`, and version tags matching `v*`.

GitHub tags and release archives are the intended distribution format. Because the repository root is the plugin root, a checkout or release archive can be installed directly without an extra packaging step.
