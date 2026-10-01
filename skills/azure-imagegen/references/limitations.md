# Limitations

This v1 skill is intentionally narrow.

## Included

- Azure OpenAI v1 only
- Image generation and image edits through the Image API
- API-key auth
- Entra ID auth through `DefaultAzureCredential`
- JSONL batch generation
- Prompt augmentation helpers
- GPT-image-2 size validation and omitted-size routing through Azure OpenAI v1 Image API
- Local ImageMagick key-color post-processing for transparent PNG cutouts

## Excluded

- Classic Azure OpenAI `api-version` endpoint patterns
- Responses API runtime support
- Direct non-Azure OpenAI endpoint support
- Auto-install into live Codex skill folders
- Icons, branding assets, CI, or packaging automation
- Speculative GPT-image-2 size-tier or token-bucket flags before Microsoft publishes Image API parameter names
- Bundled semantic background removal dependencies such as `rembg`

## Practical implications

- The CLI expects an Azure deployment name, not a raw model id.
- The deployment should target a compatible Azure OpenAI image model deployment.
- GPT-image-2 behavior is inferred only when the deployment name contains `gpt-image-2`.
- GPT-image-2 sizes over 8,294,400 pixels are passed through with a warning because Azure may resize the final image to fit.
- GPT-image-2 does not support native `background=transparent`; the CLI fails locally and points users to GPT-image-1/1.5 or `postprocess-transparent`.
- `postprocess-transparent` removes a color key with ImageMagick. It works best on pure flat backgrounds and is not a semantic segmentation tool.
- If a team needs classic endpoint support or a Responses API runtime, add that as a later versioned extension instead of bolting it onto this v1 skill.
