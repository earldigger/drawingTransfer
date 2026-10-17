# Canvas Transfer -- Python Prototype

A desktop prototype validating the workflow described in the Canvas
Transfer App project spec: photograph a drawing, correct its perspective,
overlay it on a photographed canvas with Multiply blending and a grid,
compare successive canvas photos, and save/reopen the project with
everything intact.

**This is deliberately not the target platform.** The spec calls for a
native iPhone/iPad/Mac app in Swift, SwiftUI, Core Image, AVFoundation, and
Vision. This repo is a PySide6 + OpenCV/NumPy stand-in, built to let the
actual workflow (perspective correction, nondestructive layer transforms,
blend modes, grid, compare modes) be tried and iterated on quickly in a
language/toolchain this session can run and test directly -- which Swift on
this Linux environment cannot. See "Porting to Swift" below.

## What's implemented (maps to the spec's MVP list)

- Project creation with canvas width/height/units (in/cm)
- Import image (file picker; camera capture is out of scope on desktop)
- Four-point perspective correction with draggable handles
- Move (drag on canvas or spinboxes), proportional or independent scale,
  rotate, horizontal/vertical skew -- all nondestructive (stored as
  parameters, recomputed on every render)
- Layers: add, delete, rename, reorder, show/hide, select active
- Layer opacity (0-100%) and blend mode (Normal, Multiply)
- Adjustable grid overlay: rows, columns, opacity, line thickness, with
  3x3 / 4x5 / 8x10 presets
- Compare: Overlay (the normal composite), Blink (alternate two layers on
  a timer), Split view (two layers side by side with a divider)
- Save/open as a `.ctproj` package (folder with `project.json` +
  `images/`, raw source photos only -- never baked/destructive) and
  autosave on every change once a project has been saved once

## What's intentionally skipped

- Camera capture (AVFoundation) -- desktop file import only
- Automatic rectangle detection (Vision framework) -- corners default to
  the image's own bounds; the user positions them manually
- Everything in the spec's "Future Features" list (auto-alignment,
  Difference blend, Apple Pencil, measurement tools, cloud collaboration)

## Running it

```
pip install -r requirements.txt
python -m canvastransfer.main
```

## Running the tests

```
pytest
```

31 tests cover the data model, the perspective/transform/blend/grid math in
`compositing.py`, and project save/load round-tripping. The GUI itself was
smoke-tested end-to-end under Xvfb (new project -> import -> perspective
correct -> grid -> second layer -> Multiply blend -> drag-to-move -> reorder
-> Split/Blink compare -> save -> reload into a second window) with
screenshots verified at each step.

## Architecture

```
canvastransfer/
  models.py        Project, Layer, Transform, PerspectiveCorners, GridSettings
  compositing.py    pure image ops: perspective warp, affine transform,
                     Normal/Multiply blend, grid rendering, split view
                     (this module is the Core Image stand-in)
  render.py          ties a project + its layer images into one composite
  project_io.py      save/load the .ctproj package, autosave
  ui/                PySide6 widgets (main window, canvas view, layers/
                      transform/grid/compare panels, perspective dialog)
```

`compositing.py` has no Qt dependency and is the piece most worth reading
closely before porting: its functions are pure `(numpy array, params) ->
numpy array`, which maps fairly directly onto Core Image filters/CIFilter
chains. `models.py`'s fields map directly onto the spec's "Basic Project
Data" section and are a reasonable starting point for Swift `Codable`
structs. The UI layer does not port -- it gets rewritten in SwiftUI --
but the interaction logic each panel encodes (what triggers a re-render,
proportional vs. independent scale locking, blink's timer-driven layer
swap) is worth keeping as a reference.

## Porting to Swift

This prototype exists to de-risk the *workflow*, not to be translated
line-by-line. When moving to the real Swift/SwiftUI/Core Image app:

- `models.py` -> `Codable` structs; the project package format
  (`project.json` + `images/`) can likely be kept almost as-is, or wrapped
  in a proper `FileWrapper`-based document package.
- `compositing.py` -> `CIFilter`s: `CIPerspectiveCorrection` for the
  4-point warp, `CIAffineTransform` for move/scale/rotate/skew,
  `CIMultiplyBlendMode` / `CISourceOverCompositing` for blend, and a
  custom `CIFilter` or Core Graphics draw for the grid lines.
- `render.py`'s compositing order (bottom-to-top, grid last) carries over
  directly as a `CIFilter` chain.
- Camera capture (AVFoundation) and rectangle detection (Vision) are new
  work with no prototype equivalent here, since neither is available
  outside Apple platforms.
