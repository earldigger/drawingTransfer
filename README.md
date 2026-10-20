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
- Per-layer Hue / Saturation (hue, saturation, lightness) with Colorize,
  Photoshop-style; every adjustment slider has a typeable number box
- Grid overlay: rows, columns, opacity, thickness, RGB color picker,
  3x3 / 4x5 / 8x10 presets
- Compare: Overlay, Blink Layer A only (rest of the stack stays on),
  Blink A/B (alternate), Split view
- Save/open as a `.ctproj` package; autosave (debounced) once saved

### Color Study (side panel tab)

- **Pick Color** (I): click the selected layer to add a numbered swatch.
  The sample is an average over 1, 5, 11, 21 or 41 px and is taken from
  that layer's *adjusted* image (after levels / hue-saturation), not from
  the blended composite. Clicking a numbered marker selects its swatch;
  markers move with the layer
- Swatch list with remove, undo, and saving inside the project
- Tick a swatch to highlight similar areas of its layer in yellow over a
  grayscale copy; **Highlight tolerance** is a CIELAB distance (dE76):
  about 2-3 is "just noticeable", 10-15 is "same paint mixture", 30+
  starts catching neighbouring values of the same hue
- Details: hex / RGB, CIELAB under D50 (the convention artistpigments.org
  uses), Munsell notation, value on a 0-10 scale, a warm-cool reading,
  tints / shades / tones, and the complement
- Munsell needs colors inside the Munsell renotation data; very dark,
  saturated colors (deep ultramarine, for example) show the value only
- Warm-cool and the complement are rules of thumb (CIELAB hue), not a
  standard; tints, shades and tones are mixed with Mixbox, which behaves
  like pigment rather than like light

## What's intentionally skipped

- Camera capture (AVFoundation) -- desktop file import only
- HEIC import -- export phone photos as JPEG first
- Automatic rectangle detection (Vision framework)
- Zoom/pan of the canvas view
- Everything in the spec's "Future Features" list
- Paint palette, nearest-paint matching and mixing recipes (planned as
  Color Study phase 2)

## Running it

```
pip install -r requirements.txt
python -m canvastransfer.main
```

The window freezes for about a second just after it opens while the color
library (colour-science) loads; that keeps the first color pick quick.

**License note:** Mixbox (`pymixbox`) is CC BY-NC 4.0, free for
non-commercial use only. Fine for personal use; a commercial version of
this app would need a Mixbox license or a different mixing model.

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
rules, project save/load, color math (CIELAB/Munsell checked against
artistpigments.org values), and -- rendered offscreen through the real Qt
scene -- blend-mode pixel values, layer placement, split clipping, grid
color, mouse-driven dragging, color picking and highlight pixels.

## Architecture

```
canvastransfer/
  models.py        Project, Layer (placement quad, perspective corners,
                    blend, adjustments), GridSettings, Swatch
  geometry.py       pure transform-tool math: fit, move, rotate,
                    proportional/free scale, skew, distort, flip
  image_ops.py      perspective correction, downscaling, levels,
                    hue/saturation, invert
  color_study.py    sampling, CIELAB/Munsell, warm-cool, complement,
                    tints/shades/tones (Mixbox), similar-color masks
  compare.py        how each layer displays in each compare mode
  history.py        undo/redo snapshots and transform sessions
  project_io.py     .ctproj package save/load, autosave
  ui/
    canvas_view.py   live canvas + the transform tool
    canvas_render.py layer compositing (Qt blend modes; Linear Light
                     computed from the pixels underneath) and grid
    layer_display.py cached per-layer display pixmaps and highlight overlays
    color_panel.py   Color Study tab: swatches, tolerance, details
    slider_row.py    slider + number box rows shared by the panels
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
  `CIGammaAdjust` + `CIColorMatrix` (levels), `CIHueAdjust` +
  `CIColorControls` (hue/saturation/lightness), `CIColorMonochrome`
  (colorize).
- Layer display -> each layer drawn through a `CIPerspectiveTransform`
  (quad -> canvas) and composited with `CIMultiplyBlendMode`,
  `CIScreenBlendMode`, `CILinearLightBlendMode` or
  `CISourceOverCompositing`; or `CALayer`s with a 3D transform and a
  multiply `compositingFilter` for live interaction.
- Camera capture and rectangle detection are new work with no prototype
  equivalent here.
