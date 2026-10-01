# Azure ImageGen Plugin

`azure-imagegen` is a Codex plugin with an Azure image generation skill and a bundled Python CLI. Install the repository root as the plugin; the skill also supports standalone installation.

## What it includes

- [Portable plugin manifest](./plugin.json) and [legacy Codex manifest](./.codex-plugin/plugin.json)
- [DangerMouseUK marketplace](./.agents/plugins/marketplace.json)
- [Codex skill](./skills/azure-imagegen) and [Python CLI](./skills/azure-imagegen/scripts/image_gen.py)
- Editable screenshots, validation tests, and CI

## Scope

Azure OpenAI `/openai/v1/` Image API only: generation, editing, JSONL batch generation, API keys, and Microsoft Entra ID. Local ImageMagick postprocessing can remove a flat background color.

## Install as a plugin

### Codex CLI Git installation

Register the repository marketplace, then install the plugin:

```powershell
codex plugin marketplace add dangermouseuk/azure-imagegen --ref main
codex plugin add azure-imagegen@dangermouseuk
```

The catalog is named `dangermouseuk` and points to the repository root. After an upstream update:

```powershell
codex plugin marketplace upgrade dangermouseuk
codex plugin add azure-imagegen@dangermouseuk
```

Start a new Codex chat after refreshing the plugin. Restart the desktop app when using its plugin directory. Installed plugins are cached copies; editing a separate checkout does not update that copy. Add `--json` to the installation command to see its `installedPath`. Use `codex plugin list --json` to inspect versions and enabled state.

The plugin requires a local Python environment. Follow Dependency setup below from the installed plugin directory, or use the standalone `uv run --with ...` commands in the CLI reference. Marketplace installation does not install Python packages or create Azure deployments.

### Manual local marketplace installation

Home-local checkout:

```powershell
git clone https://github.com/dangermouseuk/azure-imagegen.git "$HOME\plugins\azure-imagegen"
codex plugin marketplace add "$HOME\plugins\azure-imagegen"
codex plugin add azure-imagegen@dangermouseuk
```

For a project-local checkout, clone into `.\plugins\azure-imagegen` and register that path instead.

You can also extract a GitHub release archive and register the extracted plugin root:

```powershell
codex plugin marketplace add "C:\path\to\extracted\azure-imagegen"
codex plugin add azure-imagegen@dangermouseuk
```

Codex copies the entire local source folder, including ignored development files and Git metadata. For an active development checkout containing a .venv, credentials, or temporary files, register a clean release/archive copy instead. Keep Python environments and credential files outside the registered plugin source. .gitignore controls Git publication; it does not filter local plugin installation.

Alternatively, register the checkout in an existing personal or project marketplace. The same entry works in `~/.agents/plugins/marketplace.json` for the home-local path, or `.agents/plugins/marketplace.json` for a project-local path:

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

Merge the entry into an existing catalog rather than replacing it. Paths resolve relative to the home/project marketplace root, not the `.agents/plugins` directory. Install Azure ImageGen from the plugin directory and start a new chat. The skill triggers as `$azure-imagegen`.

The bundled repository catalog instead uses `"path": "./"`, because the repository itself is the plugin root. The portable manifest uses the [Agent Plugins schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json), with presentation metadata in `extensions.com.openai.interface`. The legacy manifest retains matching metadata for older hosts. See [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins).

## Standalone skill installation

Copy [skills/azure-imagegen](./skills/azure-imagegen) into `~/.codex/skills/azure-imagegen` or `.agents/skills/azure-imagegen`:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null
Copy-Item -Recurse ".\skills\azure-imagegen" "$HOME\.codex\skills\azure-imagegen"
```

The copied skill has no package metadata; install the equivalent runtime dependencies listed below, or use the standalone uv recipes.

## Dependency setup

Python **3.11 or later** is required. CI covers Ubuntu/Python 3.11 and 3.14, plus Windows/Python 3.14.

From the installed plugin root:

```bash
python -m pip install --upgrade -e .
```

For Entra authentication:

```bash
python -m pip install --upgrade -e ".[entra]"
```

For development and tests:

```bash
python -m pip install -e ".[dev,entra]"
```

Or use `uv sync --extra dev --extra entra` for a development checkout.

Runtime dependencies:

- `openai>=3.22.1,<4`
- `pillow>=12.3.0,<13`
- Optional `azure-identity>=1.26.0,<2` for live Entra authentication
- Optional ImageMagick `magick` executable for local color-key transparency removal

## Quick start

From the plugin root, using your Azure deployment name and its underlying model:

```powershell
python .\skills\azure-imagegen\scripts\image_gen.py generate `
  --endpoint "https://example.openai.azure.com" `
  --deployment "images-prod" `
  --image-model gpt-image-2.5-flare `
  --prompt "Minimal ceramic mug on a clean studio background" `
  --dry-run
```

Dry runs perform no network requests and create no output directories. For live calls, configure your endpoint/deployment and authentication:

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_IMAGE_MODEL     # optional capability profile for custom deployment names
```

Keep API keys in environment variables, never in command-line arguments or committed files.

## Image models

`--deployment` selects the actual Azure deployment sent to the SDK. `--image-model` selects validation capabilities without changing that deployment.

| Profile | Sizes | Quality | Editing fidelity |
| --- | --- | --- | --- |
| `gpt-image-1` / `gpt-image-1.5` | Three legacy sizes | low, medium, high | low or high |
| `gpt-image-1-mini` | Three legacy sizes | low, medium, high | Not configurable |
| `gpt-image-2` | Automatic or custom | low, medium, high | Always high; omit the flag |
| `gpt-image-2.5-sunburst` | Automatic or custom | low, medium, high, xhigh, max, auto | low or high |
| `gpt-image-2.5-flare` | Automatic or custom | low, medium, high, xhigh, max, auto | low or high |

Sunburst prioritizes editing precision; Flare prioritizes everyday generation speed. Selection precedence is JSONL `image_model` → CLI `--image-model` → `AZURE_OPENAI_IMAGE_MODEL` → deployment-name inference. Explicit `auto` resumes inference. The most specific identifier wins, including snapshot suffixes. Unknown names retain legacy capabilities with a warning.

- Defaults remain **high quality, PNG, and one image**. Image 2/2.5 omit size by default and accept `--size auto`. Legacy profiles default to `1024x1024` and accept `1536x1024` or `1024x1536`.
- Custom dimensions must be multiples of 16, neither edge above 3,840, aspect ratio at most 3:1, and total pixels 655,360–8,294,400. Larger requests fail locally. Image 2.5 resolutions above 3,686,400 pixels are labeled experimental.
- Native transparency requires PNG. Image 2 transparency is opt-in through `--background transparent` and warns about preview/Azure availability. Image 2.5 accepts native transparency.
- Azure output supports PNG and JPEG, not WEBP. Compression is JPEG-only.
- `--input-fidelity` is edit-only. Omit it for Image 2 and Mini.
- Batch requests are validated after job overrides; one invalid job prevents all API calls. Existing outputs and overlapping paths are checked before live requests.

Capabilities checked **1 October 2026** against the [Microsoft image guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/dall-e) and [OpenAI image reference](https://developers.openai.com/api/reference/resources/images/methods/generate). Microsoft documentation mixes older and newer examples; resource access and preview availability still depend on your Azure deployment. OpenAI retirement dates do not establish Azure retirement dates.

Fallback for an image already generated on a pure flat key color:

```powershell
python .\skills\azure-imagegen\scripts\image_gen.py postprocess-transparent `
  --input ".\output\imagegen\product-keyed.png" `
  --out ".\output\imagegen\product-transparent.png" `
  --key-color "#00FF00" `
  --fuzz 6 `
  --trim
```

## References and limitations

- [CLI reference](./skills/azure-imagegen/references/cli.md)
- [Azure authentication](./skills/azure-imagegen/references/azure-auth.md)
- [Prompting guidance](./skills/azure-imagegen/references/prompting.md)
- [Sample prompts](./skills/azure-imagegen/references/sample-prompts.md)
- [Limitations](./skills/azure-imagegen/references/limitations.md)

Version 0.3.0 retains Azure v1 Image API workflows. Streaming, Responses API, direct non-Azure endpoints, automatic model deployment, and bundled semantic segmentation are outside this release.

## Validation and distribution

```bash
python -m pip install -e ".[dev,entra]"
pytest
```

Optional skill metadata validation, when the Codex skill-creator tooling is installed:

```bash
python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/azure-imagegen
```

GitHub Actions runs tests on pull requests, pushes to `main`, and `v*` tags. Tests use mocked SDK requests and do not spend Azure credits.

Git checkouts and GitHub release archives are the distribution format. The repository root is the plugin root; no Python executable package or PyPI publication is required.
