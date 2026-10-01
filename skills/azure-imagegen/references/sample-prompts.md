# Sample prompts

Use these as starting points only. Keep user-provided constraints and avoid inventing new creative elements.

## Generate

### photorealistic-natural

```text
Use case: photorealistic-natural
Primary request: candid photo of an elderly sailor on a small fishing boat adjusting a net
Scene/background: coastal water with soft haze
Subject: weathered skin with wrinkles and sun texture; a calm dog on deck nearby
Style/medium: photorealistic candid photo
Composition/framing: medium close-up, eye-level, 50mm lens
Lighting/mood: soft coastal daylight, shallow depth of field, subtle film grain
Materials/textures: real skin texture, worn fabric, salt-worn wood
Constraints: natural color balance; no heavy retouching; no glamorization; no watermark
Avoid: studio polish; staged look
```

### product-mockup

```text
Use case: product-mockup
Asset type: ecommerce hero image
Primary request: premium product photo of a matte black shampoo bottle with a minimal label
Scene/background: clean studio gradient from light gray to white
Subject: single bottle centered with subtle reflection
Style/medium: premium product photography
Composition/framing: centered, slight three-quarter angle, generous padding
Lighting/mood: softbox lighting, clean highlights, controlled shadows
Materials/textures: matte plastic, crisp label printing
Constraints: no logos or trademarks; no watermark
```

### ui-mockup

```text
Use case: ui-mockup
Asset type: mobile app concept
Primary request: mobile app UI for a local farmers market with vendors and specials
Scene/background: clean white background with subtle natural accents
Subject: header, vendor list with small photos, today's specials section, location and hours
Style/medium: realistic product UI, not concept art
Composition/framing: iPhone frame, balanced spacing and hierarchy
Constraints: practical layout, clear typography, no logos or trademarks, no watermark
```

### infographic-diagram

```text
Use case: infographic-diagram
Primary request: detailed infographic of an automatic coffee machine flow
Scene/background: clean light neutral background
Subject: bean hopper -> grinder -> brew group -> boiler -> water tank -> drip tray
Style/medium: clean vector-like infographic with clear callouts and arrows
Composition/framing: vertical poster layout, top-to-bottom flow
Text (verbatim): "Bean Hopper", "Grinder", "Brew Group", "Boiler", "Water Tank", "Drip Tray"
Constraints: clear labels, strong contrast, no logos or trademarks, no watermark
```

### stylized-concept

```text
Use case: stylized-concept
Asset type: landing page hero
Primary request: minimal abstract background with soft geometric forms and restrained motion cues
Style/medium: matte illustration with subtle depth
Composition/framing: wide composition with large negative space on the right for headline text
Lighting/mood: soft studio glow, calm and modern
Color palette: cool neutrals with a muted teal accent
Constraints: no text; no logos; no watermark
Avoid: glossy plastic; neon gradients; clutter
```

## Edit

### text-localization

```text
Use case: text-localization
Input images: Image 1: original infographic
Primary request: translate all in-image text to Spanish
Constraints: change only the text; preserve layout, typography, spacing, and hierarchy; no extra words; do not alter logos or imagery
```

### identity-preserve

```text
Use case: identity-preserve
Input images: Image 1: person photo; Image 2..N: clothing items
Primary request: replace only the clothing with the provided garments
Constraints: preserve face, body shape, pose, hair, expression, and identity; match lighting and shadows; keep background unchanged; no accessories or text
```

### precise-object-edit

```text
Use case: precise-object-edit
Input images: Image 1: room photo
Primary request: replace only the white chairs with wooden chairs
Constraints: preserve camera angle, room lighting, floor shadows, and surrounding objects; keep all other aspects unchanged
```

### background-extraction

```text
Use case: background-extraction
Input images: Image 1: product photo
Primary request: extract the product on a transparent background
Constraints: crisp silhouette, no halos or fringing; preserve label text exactly; no restyling
```

### gpt-image-2-key-color-cutout

```text
Use case: background-extraction
Primary request: create the product as an isolated cutout on a flat pure #00FF00 background
Constraints: no shadows, no reflections, no gradients, no green in the product, crisp silhouette, centered subject, preserve label text exactly
Output intent: run postprocess-transparent with key color #00FF00 to create a transparent PNG
```

### compositing

```text
Use case: compositing
Input images: Image 1: base scene; Image 2: subject to insert
Primary request: place the subject from Image 2 next to the person in Image 1
Constraints: match lighting, perspective, and scale; keep background and framing unchanged; no extra elements
```

### sketch-to-render

```text
Use case: sketch-to-render
Input images: Image 1: drawing
Primary request: turn the drawing into a photorealistic image
Constraints: preserve layout, proportions, and perspective; choose realistic materials and lighting; do not add new elements or text
```
