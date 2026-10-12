# Kutscherei cover source

Retrieved over SSH from `kutscherei.local`, from the Falz app at
`/Volumes/iMac/programmier-projekte/ga`.

The files listed in `source-manifest.json` are unchanged copies, verified
against SHA-256 checksums read directly from Kutscherei. This app directory has
no Git metadata; the manifest records paths and file hashes instead of a commit.

The original cover composition is in `app/Sources/FalzApp/LibraryView.swift`
(`BookCover`, lines 252–277). Its cloth, foil, image cache, fonts, and colors are
defined in `Theme.swift`; `AppModel.swift` and `FalzCore/Library.swift` supply
category and resource lookup. `assets/textures` contains the original category
metadata, all linen/gold tiles, and their generation and verification scripts.
The font files and their SIL Open Font License notices were copied from the
source project's `output/falz-icons/fonts` directory into `assets/fonts`.

The native adapter is `apple/GA/KutschereiBookCover.swift` in this repository.
It retains the original cover composition and uses the current app's titles
and GA labels. Resource lookup uses bundled `CoverMaterials` and `CoverFonts`
directories; CoreText registers the four font faces on iOS and macOS. Artwork
lettering uses fixed font sizes, while the accessible labels beside the covers
continue to follow Dynamic Type. Categories come from the original GA ranges;
unknown numbers use the source app's neutral color. Category colors are the
original digital approximations documented by the source project.

The unchanged Falz source is a reference snapshot, not a second compiled app.
The current app bundles the 14 linen tiles, shared gold foil, category metadata,
four fonts, and both font license notices for offline rendering.

To check the original texture files on macOS:

```sh
swift vendor/kutscherei-covers/assets/textures/verify.swift
```
