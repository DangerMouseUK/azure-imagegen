# Limitations

## Included

- Azure OpenAI v1 Image API generation, editing, and JSONL batch generation
- API keys and Microsoft Entra ID through DefaultAzureCredential
- Explicit model capability profiles for GPT Image 1, 1 Mini, 1.5, 2, 2.5 Sunburst, and 2.5 Flare
- Prompt augmentation, optional downscaling, and ImageMagick color-key removal
- Portable plugin packaging and legacy Codex compatibility

## Runtime boundaries

No classic Azure api-version endpoint mode, Responses API, streaming, direct OpenAI endpoints, automatic Azure deployments, or bundled semantic background removal.

The CLI sends the Azure deployment name as the SDK model field. The capability profile is local validation metadata, not an Azure deployment change or availability check. Unknown deployment names retain legacy behavior; select the underlying model explicitly for modern options.

## Azure-specific limits

- Output: PNG or JPEG only. WEBP output fails locally.
- Native transparency: PNG only. GPT Image 2 transparency is preview and requires explicit background=transparent; actual support depends on the Azure deployment. Image 2.5 accepts native transparent PNG.
- Custom sizes for Image 2/2.5: multiples of 16, maximum edge 3,840, aspect ratio no greater than 3:1, and 655,360–8,294,400 pixels. Invalid explicit dimensions fail before requests, rather than relying on automatic resizing.
- Image 2.5 above 3,686,400 pixels is experimental. Automatic sizing may return dimensions outside explicit-size rules.
- Image 2.5 quality: low, medium, high, xhigh, max, auto. Earlier profiles use Azure's documented low/medium/high. GPT Image 2 quality=auto remains unconfirmed in Microsoft's capability table.
- Compression: integer 0–100, JPEG only.
- Input fidelity: low/high only where configurable. Omit it for GPT Image 2 (always high) and Mini (unsupported).
- Local validation cannot establish regional access, deployment readiness, quotas, or Azure pricing. No automatic fallback to another deployment is performed.

## Documentation and model lifecycle

Checked **1 October 2026**:

- [Microsoft image generation guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/dall-e)
- [Azure model lifecycle policy](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements)
- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI image reference](https://developers.openai.com/api/reference/resources/images/methods/generate)

Microsoft's page mixes older examples with newer capability tables. This plugin follows Azure output restrictions and explicitly labels previews. OpenAI API model retirement dates do not establish Azure retirement dates; check the lifecycle of the actual Azure deployment before migrating.

## Color-key fallback

postprocess-transparent removes a flat background color with ImageMagick. It works best on pure backgrounds without the key color in the subject. Hair, glass, shadows, and soft edges may need semantic segmentation or manual editing; neither is bundled.
