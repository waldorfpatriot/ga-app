# GA material textures

`categories.json` is the integration contract for the library UI. Every path in it is relative to this directory.

- `linen/<category-id>.png`: seamless 512 × 512 sRGB linen tile
- `gold/<category-id>.png`: seamless 512 × 512 sRGB gold-foil tile, with a stable variation for that category
- `gold/gold-foil.png`: neutral gold-foil fallback
- `overview.png`: all linen and gold materials in catalogue order
- `generate.swift`: deterministic source generator
- `verify.swift`: dimension, decoding and seam-statistic check

Regenerate and verify on macOS:

```sh
swift assets/textures/generate.swift
swift assets/textures/verify.swift
```

Use the gold image through the alpha mask of the title, GA number or ornament. The gold tiles themselves are opaque because that makes them usable with SwiftUI `ImagePaint`, Core Graphics masks and CSS masks without premultiplied-alpha edge artifacts.

The colors are digital approximations from publisher cover photographs, not official color specifications. See `docs/research/book-design.md` for provenance and limitations.
