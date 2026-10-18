# Canvas Transfer -- Python Prototype

A desktop prototype validating the workflow described in the Canvas
Transfer App project spec: photograph a drawing, correct its perspective,
overlay it on a photographed canvas with Multiply blending and a grid,
compare successive canvas photos, and save/reopen the project with
everything intact.

**This is deliberately not the target platform.** The spec calls for a
native iPhone/iPad/Mac app in Swift, SwiftUI, Core Image, AVFoundation, and
Vision. This repo is a PySide6 + OpenCV/NumPy stand-in, built so the
workflow can be tried and iterated on quickly. See "Porting to Swift" below.

## What's implemented

- Project creation with canvas width/height/units (in/cm)
- Image import (file picker); phone photos are rotated upright from their
  EXIF orientation
- Four-point perspective correction with draggable handles, either keeping
  the photo's proportions (drawings) or stretching to fill the canvas
  (photos of the canvas itself)
- Imported images are fitted inside the canvas (never cropped) and open
  with the transform box active
- Fresco-style transform tool: 8 handles plus a rotation handle; drag
  inside the box to move; modes **Proportional**, **Free** (independent
  width/height), **Skew**, **Distort**; Flip Horizontal/Vertical; Fit to
  Canvas. Content pushed past the canvas edge is hidden, not lost, and
  shows faintly while the box is active
- Transform sessions: turning Transform on (T) starts one; **Done**
  (Return) keeps it as a single undo step, **Cancel** (Esc) reverts
  everything since Transform was turned on. Any non-transform edit
  finishes the session first; switching layers continues on the new layer
- Undo/Redo (Cmd+Z / Shift+Cmd+Z) for every project edit; a slider drag
  is one step. Compare-mode settings are not undoable (viewing choice)
- Layers: add, delete, rename (double-click), reorder, show/hide, select
- Per-layer opacity and blend mode: Normal, Multiply, Screen, Linear Light
- Per-layer Levels (dark point, midtones, light point) and Invert values
- Per-layer Color & Vibrance: temperature, vibrance, saturation
- Grid overlay: rows, columns, opacity, thickness, RGB color picker,
  3x3 / 4x5 / 8x10 presets
- Compare: Overlay, Blink Layer A only (rest of the stack stays on),
  Blink A/B (alternate), Split view
- Save/open as a `.ctproj` package; autosave (debounced) once saved

## What's intentionally skipped

- Camera capture (AVFoundation) -- desktop file import only
- HEIC import -- export phone photos as JPEG first
- Automatic rectangle detection (Vision framework)
- Zoom/pan of the canvas view
- Everything in the spec's "Future Features" list

## Running it

```
pip install -r requirements.txt
python -m canvastransfer.main
```

### macOS: "Could not find the Qt platform plugin 'cocoa'"

If the app aborts with this message even though the plugin file exists,
check whether the files inside `.venv` carry macOS's hidden flag
(`ls -lO .venv/lib/python3.12/site-packages/PySide6/Qt/plugins/platforms/`
shows `hidden`). Qt skips hidden files when it scans for plugins. Clear the
flag with:

```
chflags -R nohidden .venv
```

## Running the tests

```
pytest
```

The suite covers the transform geometry, image operations, compare-mode
rules, project save/load, and -- rendered offscreen through the real Qt
scene -- blend-mode pixel values, layer placement, split clipping, grid
color, and mouse-driven dragging.

## Architecture

```
canvastransfer/
  models.py        Project, Layer (placement quad, perspective corners,
                    blend, contrast, invert), GridSettings
  geometry.py       pure transform-tool math: fit, move, rotate,
                    proportional/free scale, skew, distort, flip
  image_ops.py      perspective correction, downscaling, contrast/invert
  compare.py        how each layer displays in each compare mode
  history.py        undo/redo snapshots and transform sessions
  project_io.py     .ctproj package save/load, autosave
  ui/
    canvas_view.py   live canvas + the transform tool
    canvas_render.py layer compositing (Qt blend modes; Linear Light
                     computed from the pixels underneath) and grid
    layer_display.py cached per-layer display pixmaps
    main_window.py   toolbar, menus, wiring; plus the side panels
```

A layer's placement is four canvas points (its "quad"), stored as
fractions of the canvas size. Every transform mode just moves those
points, and the layer image is mapped onto them with a projective
transform, so all edits stay nondestructive and repeatable. Source photos
are stored untouched; perspective correction and adjustments are
recomputed for display and cached.

## Porting to Swift

- `models.py` -> `Codable` structs; the `.ctproj` layout (`project.json` +
  `images/`) can carry over, likely wrapped in a `FileWrapper` package.
- `geometry.py` -> a plain Swift module; it has no dependencies and is the
  most directly portable piece.
- `image_ops.py` -> `CIPerspectiveCorrection`, `CIColorInvert`,
  `CIGammaAdjust` + `CIColorMatrix` (levels), `CITemperatureAndTint`,
  `CIVibrance`, `CIColorControls` (saturation).
- Layer display -> each layer drawn through a `CIPerspectiveTransform`
  (quad -> canvas) and composited with `CIMultiplyBlendMode`,
  `CIScreenBlendMode`, `CILinearLightBlendMode` or
  `CISourceOverCompositing`; or `CALayer`s with a 3D transform and a
  multiply `compositingFilter` for live interaction.
- Camera capture and rectangle detection are new work with no prototype
  equivalent here.
