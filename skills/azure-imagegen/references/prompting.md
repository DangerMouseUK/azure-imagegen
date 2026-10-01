# Prompting best practices

## Structure

- Use a consistent order: scene/background -> subject -> key details -> constraints -> output intent.
- Include intended use such as ad, UI mockup, infographic, product shot, or logo concept.
- For complex requests, prefer short labeled lines over one large paragraph.

## Specificity

- Name materials, textures, and medium: photo, watercolor, vector, painted icon, matte 3D render.
- For photorealism, include framing, lens, lighting, and texture cues.
- Add targeted quality cues only when needed; avoid generic "8K" style fluff.

## Avoid tacky outputs

- Avoid vague hype words unless the user explicitly wants them.
- Ask for restraint when appropriate: `editorial`, `premium`, `subtle`, `natural color grading`, `soft contrast`.
- Add a short `Avoid:` line when the model drifts toward clutter, fake-looking people, oversharpening, or cheesy effects.

## Composition and layout

- State framing and placement explicitly.
- Call out negative space when the image must leave room for UI, a headline, or other overlays.
- For UI mockups, describe real sections and content hierarchy so the output feels shippable, not conceptual.

## Constraints and invariants

- Say what must not change.
- For edits, use the pattern `change only X; keep Y unchanged`.
- Repeat invariants on each iteration to reduce drift.

## Text in images

- Put exact text in quotes.
- Specify placement and typography when it matters.
- If a word is tricky, spell it letter-by-letter in the prompt.

## Multi-image edits

- Reference inputs by index and role.
- Describe exactly how to combine them.
- For compositing, specify lighting, scale, and perspective constraints.

## Iterate deliberately

- Start from a clean base prompt.
- Change one thing at a time between runs.
- Re-specify the most important constraints on every rerun.

## Quality and latency

- Start with `quality=low` for quick exploration.
- Use `quality=high` for text-heavy or detail-critical outputs.
- Use `input_fidelity=high` for strict identity or layout preservation.

## Taxonomy hints

Generate:
- `photorealistic-natural`: use photography language and real-world texture
- `product-mockup`: prioritize label clarity and silhouette
- `ui-mockup`: describe believable app structure and hierarchy
- `infographic-diagram`: define layout flow and exact text
- `logo-brand`: keep it simple, scalable, and high-contrast
- `stylized-concept`: specify finish, material cues, and restraint

Edit:
- `text-localization`: change only text; preserve layout
- `identity-preserve`: lock identity, pose, and body shape
- `precise-object-edit`: name the exact object to remove or replace
- `background-extraction`: ask for crisp edges and no halos
- `compositing`: specify scale, lighting, and perspective match

## See also

- `references/sample-prompts.md`
