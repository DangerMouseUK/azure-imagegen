# TODO

## Revisit When Microsoft Updates GPT-image-2 Docs

- Re-check Azure GPT-image-2 Image API parameter support against official Microsoft Learn docs.
- Confirm whether Azure supports `webp` output for Image API v1, or only `png` and `jpeg`.
- Confirm whether GPT-image-2 should allow `quality=auto` on Azure, and whether omitting `quality` is preferred over sending `high`.
- Watch for any future GPT-image-2 native `background=transparent` support; currently the CLI rejects it locally.
- Confirm whether Azure GPT-image-2 supports `stream` and `partial_images`, and whether a preview header is required.
- Confirm whether Azure GPT-image-2 supports explicit `size=auto` or only omitted `size` for routing.
- Confirm whether Azure documents max edge and aspect-ratio constraints for GPT-image-2, not only total pixel budget and 16px alignment.
- Add docs/tests for any confirmed Azure-specific behavior.

## Inconsistencies To Raise With Microsoft Azure

- Microsoft Learn image-generation page does not yet include GPT-image-2, while the Microsoft Foundry blog says GPT-image-2 is generally available and rolling out.
- Azure docs mix older deployment-scoped `?api-version=...` examples with newer `/openai/v1/` OpenAI-compatible examples.
- Azure Image API docs say WEBP is not supported, while OpenAI docs support WEBP and some Azure/Foundry examples imply broader format support.
- GPT-image-2 blog mentions routing modes, legacy size tiers, and token buckets, but does not publish request parameter names for controlling them.
- GPT-image-2 blog says over-budget requests are automatically resized, while OpenAI docs describe a hard maximum pixel constraint.
- Azure docs mention streaming/`partial_images` for image generation, but examples use preview headers and do not clarify model/version availability for GPT-image-2.
- Azure docs document transparent backgrounds for GPT-image-1 series, but do not state clearly that GPT-image-2 rejects `background=transparent`.

## Transparency Workaround Notes

- GPT-image-2 native transparency is unsupported in current OpenAI docs and not documented as supported by Azure.
- The CLI uses `postprocess-transparent` plus ImageMagick `magick` for explicit flat key-color removal.
- `rembg` or another segmentation tool may produce better results for hair, glass, soft edges, shadows, or non-flat backgrounds, but it is intentionally not bundled.
