# Azure authentication

This skill supports two live authentication modes.

## 1. API key mode

Default mode:

```text
--auth-mode api-key
```

Default env vars:

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT
AZURE_OPENAI_API_KEY
```

Use custom env-var names when a team already standardizes different names:

```powershell
python .\skills\azure-imagegen\scripts\image_gen.py generate `
  --endpoint-env "TEAM_AZURE_OPENAI_ENDPOINT" `
  --deployment-env "TEAM_AZURE_OPENAI_DEPLOYMENT" `
  --api-key-env "TEAM_AZURE_OPENAI_API_KEY" `
  --prompt "Editorial product shot of a travel flask" `
  --dry-run
```

Rules:

- Prefer environment variables instead of secret CLI flags.
- Pass the variable name to `--api-key-env`, never the key itself.
- Keep endpoint and deployment values non-secret.
- Treat the API key as secret and never paste it into chat.
- Credential values and location details are omitted from diagnostics and dry-run previews.

## 2. Entra ID mode

Enable Entra auth with:

```text
--auth-mode entra
```

Live Entra-authenticated calls require:

```bash
python -m pip install "azure-identity>=1.26.0,<2"
```

Or:

```bash
uv pip install "azure-identity>=1.26.0,<2"
```

The CLI uses `DefaultAzureCredential`, so any supported local or hosted credential source can satisfy auth.

Default token scope:

```text
https://ai.azure.com/.default
```

Override the scope only when the environment requires it:

```powershell
python .\skills\azure-imagegen\scripts\image_gen.py generate `
  --auth-mode entra `
  --entra-scope "https://ai.azure.com/.default" `
  --prompt "Minimal product photo of a brass desk lamp" `
  --dry-run
```

## Endpoint guidance

The CLI accepts either:

- the Azure resource root, such as `https://example.openai.azure.com`
- the full Azure OpenAI v1 base URL, such as `https://example.openai.azure.com/openai/v1/`

The CLI normalizes the root resource URL to `/openai/v1/`.

## Deployment guidance

Pass the Azure deployment name, not the raw model id. The deployment should point at a compatible Azure OpenAI image model deployment.

For a custom name such as images-prod, also set --image-model or AZURE_OPENAI_IMAGE_MODEL
to its underlying model identifier (for example, gpt-image-2.5-flare). This selects local
validation capabilities and does not change the Azure deployment or authentication.

## Failure modes

- Missing endpoint: set `AZURE_OPENAI_ENDPOINT` or pass `--endpoint`
- Missing deployment: set `AZURE_OPENAI_DEPLOYMENT` or pass `--deployment`
- Missing API key in `api-key` mode: set `AZURE_OPENAI_API_KEY` or pass `--api-key-env` to use a different env var name
- Missing `azure-identity` in `entra` mode: install `azure-identity`
