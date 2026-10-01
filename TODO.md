# TODO

## Follow Azure documentation changes

Capabilities were reviewed on **1 October 2026** for version 0.3.0.

- Confirm GPT Image 2 quality=auto on Azure; its current capability table lists low/medium/high.
- Monitor deployment/region availability and stability of GPT Image 2 native transparency. The CLI permits explicit transparent PNG requests with a preview warning.
- Revisit WEBP only if Microsoft explicitly supports it in the Azure Image API.
- Recheck model-specific input-fidelity behavior as Azure clarifies its 2.5 documentation.
- Track Azure retirement notices independently of OpenAI API retirement dates.

## Possible later extensions

These are outside version 0.3.0:

- Image API streaming and partial previews
- Responses API conversational editing
- Published Azure size-tier/token-bucket controls, if documented
- Optional semantic background removal; retain ImageMagick color-key removal without adding segmentation dependencies

## Sources

- [Microsoft image guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/dall-e)
- [Azure lifecycle policy](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements)
- [OpenAI image guide](https://developers.openai.com/api/docs/guides/image-generation)
