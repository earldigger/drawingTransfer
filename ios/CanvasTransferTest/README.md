# Canvas Transfer — iPad test app

A small iPad app that tests the three things the Python prototype can't:

1. **Live rectangle detection** — Apple Vision outlines the canvas or paper in
   the camera view, and finds the corners again on the photo you take.
2. **Pencil and touch** — dragging corners with a loupe, and moving, pinching
   and twisting a reference into place.
3. **Color on the iPad** — images at Multiply 60 % (with auto levels),
   stacked as layers, opacity, and full screen.

It is not the app: projects are kept on the iPad only (no iCloud), and the
iPad's paint library is its own copy. Each project is saved as you work, and
the one you had open reopens at launch; deleting the app deletes them. Names
and defaults follow `docs/design/README.md`.

## Run it on your iPad

Needs Xcode 16 or later (the project uses folder-synced groups) and an iPad on
iPadOS 17 or later.

1. Open `ios/CanvasTransferTest/CanvasTransferTest.xcodeproj` in Xcode.
2. Select the **CanvasTransferTest** target → **Signing & Capabilities**:
   - **Team**: your Apple ID (Xcode → Settings → Accounts to add it; a free
     account works, the app then runs for 7 days before you reinstall it).
   - **Bundle Identifier**: change `com.example.CanvasTransferTest` to
     something of your own, e.g. `com.yourname.CanvasTransferTest`.
3. Connect the iPad with a cable, unlock it, and trust the Mac. The first time,
   turn on **Settings → Privacy & Security → Developer Mode** on the iPad and
   restart it.
4. Choose the iPad as the run destination at the top of the Xcode window and
   press **Run** (⌘R). The first time, the iPad may ask you to trust the
   developer: **Settings → General → VPN & Device Management**.

The Simulator runs it too, but has no camera: use **Photos** there.

New `.swift` files dropped into `CanvasTransferTest/` are picked up by Xcode
automatically.

## What to try

- **Gallery**: at the top, sizes to start from: **Recent** (your paintings'
  sizes) or **Saved** (yours, then the standard 8 × 10 to 36 × 48), and
  **Custom size**; each card's ⌄ menu saves, renames or deletes it. Tapping
  one opens **New project** on the right: name, unit (inches or cm), width and
  height with a lock, orientation, background (white, black or medium gray,
  under the layers everywhere) and Save this size. Below, your paintings, the
  most recent first; long-press one to rename, duplicate or delete it. The
  **house** at the top left goes back; each project keeps its own layers, swatches and grid.
- **iPhone** (the same app, upright only): the Gallery in one column, New
  project in a sheet; in a project the tools are in a row at the bottom: **+** (a
  pop-up with Camera and Photos), Transform / Crop (a pop-up; the button
  shows the one that's on), Grid, Compare and **Layers** (the layer
  panel at the side, thumbnails with ‹ to expand, and the layer bar at the
  bottom, on and off together), and each bar stacks into rows. On the phone, Adjust opens a strip above the layer bar: invert,
  black, mid, white, hue, saturation, lightness, colorize and reset, with a
  thin slider along its top for the chosen one. The layer panel scrolls past
  8 layers, Flatten staying put. Camera puts the shutter
  at the bottom; Adjust corners has its panel under the photo. Not on the
  phone yet: Swatches / Simplify / Highlight, the swatch panel, the Paint
  library and the swatch sheet PDF.
- **Where projects are kept** (the menu at the Gallery's top right): on this
  iPad, or **Choose a folder…** in Files, e.g. iCloud Drive > Canvas Transfer.
  iCloud syncs that folder (no iCloud entitlement needed, so it works with a
  free developer account) and it shows in Finder on the Mac. Choosing it can
  move the iPad's projects into it; a project still in the cloud downloads
  when you open it. **Keep projects on this iPad** switches back (the
  folder's projects stay in the folder).
- **Top bar**: the house; in the middle the tools (+ with Camera and
  Photos, Transform / Crop, Grid, Compare, Pencil, the color tool; the
  combined ones open a pop-up below); on the right undo and
  redo, Paint library, Share and Full screen. Each tool with a bar at the
  bottom turns the others off.

- **Camera** (top bar): point at the canvas on the easel. Does the blue
  outline find it — in studio light, at an angle, with a busy background?
  Note when it fails.
- Take the photo: are the corners already right? Drag them — is the loupe
  where you need it, with finger and with Pencil?
- **Reset** puts the corners at the photo's edges; **Detected outline**
  brings back what Vision found. **Find rectangle** (on the camera, and in
  Adjust corners) turns detection off; it's remembered.
- **Add layer**: every image lands at Multiply 60 % with auto levels and
  Transform on: one finger moves it, pinch scales, twist rotates.
- **Crop** (top bar): drag the corners or edge middles, or
  inside the frame to slide it; what's cut off shows faintly. Free or
  Original; Reset; Cancel or Done. The crop moves, scales and turns with the
  image, and Crop again brings back what you cut.
- **The color tool** (eyedropper, top bar) opens the color bar. On its left,
  three tools, each on (lavender) until tapped again, with its options in a
  pop-up above it:
  **Eyedropper** (sample size 1, 5 or 11 px): touch the canvas for a loupe on
  the selected layer and lift to add a numbered swatch; two fingers pan and zoom.
  **Simplify**: upright Steps (1–24) and Smoothing sliders, Colors or Values
  (tap the tile again, or ⌄, to hide the options and stay simplified; Off ends it);
  the eyedropper then reads the flat color you see.
  **Highlight**: each swatch's range in its own bright color over gray, with
  an upright Range slider and All or Selected.
  Then the chips (long-press to delete one); on the right, the pin hides or
  shows the swatch markers, the trash deletes all swatches (asks first), and
  Done. Choosing a swatch selects its layer and opens its panel, which points
  at that layer.
- **Pencil** (iPad top bar): draw with Apple Pencil or a finger (while it's
  on, pinch and pan don't move the canvas: zoom first). A panel at the left
  has Size (1–300 px of the drawing layer; past the ink's widest, the sheet
  is drawn smaller and magnified), Opacity and Color (one pop-up: a hue ring
  and shade disc, and a History of the last 10 colors chosen, with Clear). No Done: it draws until
  turned off. Undo takes back strokes one at a time. The strokes go into the
  selected drawing layer (or a new "Drawing n" on top) when you choose
  another layer, add one, or put the Pencil away. Thumbnails have a
  checkerboard behind see-through parts.
- **New layer** (+, below Flatten in the layer bar): an empty, transparent
  "Drawing n" on top, filling the canvas; the Pencil draws into it.
- **Flatten** (bottom of the layer bar): the visible layers exactly as shown
  (opacity, blend, Look, crop, transform) become one new, ordinary layer,
  "Flattened 1", on top at Normal 100 %, filling the canvas; the layers in it
  are hidden, not deleted. Swatches, Simplify and Highlight on it read what
  you see; on a layer that isn't at Normal 100 % they show a hint to flatten.
- **Details | Paints & mixes** (the swatch panel): hex, RGB, Lab, value, warm
  or cool, complement, and Mixbox tints, shades and tones; then Mix from (a
  palette, all your paints of a medium, or a classic palette filled from your
  paints), Lighten with (a white, water or nothing), Favorites only, and the
  three best two-paint mixes and three best of three paints plus the
  lightener, each with ΔE and a thin bar showing the amounts in the paints'
  colors. Each paint's brand and notes are behind its
  paint icon, orange when there's a note (a stand-in's color, or off screen).
- **Paint library** (top bar, after Redo): Paints and Palettes, full screen,
  Cancel or Save. Paints: the table with ★ and Use, Add Paint…, Edit… (the
  prototype's Edit Paint: group, brand, name, series, pigments, opacity,
  lightfastness, drying, strength, Lab color or hex, stand-in), Delete, Revert to
  Site Data, Open Web Page, Import paints… (a newer paints.json from the
  prototype). Palettes: yours and the classic ones; New, Edit, Duplicate as
  My Palette, Delete. Save keeps the library on the iPad, in the prototype's
  format; the Mac's paints.json isn't changed.
- **Share swatch sheet (PDF)** (top right): the canvas with its numbered
  swatches, and each swatch's numbers and best mixes, to print or keep at the easel.
- A small purple circle on a layer thumbnail's left edge means it has swatches.
- **Transform**: a bar with Proportional, Distort, Free and Skew for the
  corner and edge handles (Proportional also has a rotate handle above the
  top edge), Flip H / V, Fit, Cancel and Done. Fingers move,
  pinch and twist in every mode. Placement is four corners, as in the prototype.
- **Undo / redo**: the top-bar buttons, a two-finger tap to undo, a
  three-finger tap to redo, or ⌘Z / ⇧⌘Z. A gesture, an opacity drag or a
  whole crop is one step; selecting a layer isn't.
- **Adjust** (bottom bar): invert, levels, hue / saturation or colorize,
  lightness, as in the prototype; live, saved and undoable. Blend has Normal,
  Multiply and Screen.
- **Compare** (top bar): Blink A (A fades in and out), Blink A / B (a
  crossfade), or Split with a draggable line; A and B, swap, speed, pause. The layer bar numbers the layers and
  marks A and B.
- **Layers** (right): ‹ expands the bar to numbers, eyes and blend ·
  opacity. Tap a thumbnail to select it, double-tap to show or hide it. Long-press a layer to move it up or down, to the front or back,
  duplicate, hide or delete it. The layer bar at the bottom has the layer's
  name, opacity, blend, Adjust, Flip horizontal / vertical, and **⋯** with Fit
  and **Edit corners…**, which reopens Adjust corners
  on the original photo (kept since this build) and keeps the placement.
- **Grid** (top bar): on / off, rows and columns (1–10), Square cells,
  color and opacity.
  It's saved with the session but isn't an undo step.
- **Share** (top right): the canvas as a full-resolution JPEG, with or
  without the grid, through the share sheet (AirDrop to the Mac, Files).
- Compare the colors with the Mac prototype and with the real canvas.
- **Full screen** (top right) for working at the easel; the faint button
  top-left comes back.
- Photos (top bar) adds an image from your library.

## Files

| File | What it does |
|---|---|
| `CanvasTransferTestApp.swift` | App entry |
| `Projects.swift` | Projects (one folder each), the Gallery, New project, and the app's root |
| `Autosave.swift` | Saves a project's session (session.json, a PNG per layer, photos) and opens it |
| `History.swift` | Undo and redo: a step per settled change, holds for gestures, drags and crops |
| `Flatten.swift` | Flatten and Update: the visible layers rendered into one layer, swatches read again |
| `Look.swift` | Adjustments (prototype's order and ranges) with Core Image; the Adjust popover |
| `Mixbox.swift`, `mixbox_lut.bin` | Mixbox 2.0 ported from pymixbox (CC BY-NC 4.0, personal use) and its lookup table |
| `Mixing.swift` | Lab D50, CIEDE2000, and the recipe search, as in the prototype's mixing.py |
| `Model.swift` | Layer (look, placement), the session, canvas sizes |
| `ImageOps.swift` | Upright photos, perspective correction, auto levels, rectangle detection |
| `Camera.swift` | Live camera with detection overlay; Capture screen |
| `CornersScreen.swift` | Adjust corners (handles, loupe); the capture flow |
| `PaintLibraryView.swift` | The Paint library: Paints table and editor, Palettes and editor |
| `Paints.swift`, `paints.json` | Your paint library from the prototype, its stand-ins and whites; Import paints… |
| `Strength.swift` | Paint strength from a photo of a tint, kept on the iPad; Measure strength sheet |
| `SwatchSheet.swift` | The swatch sheet PDF |
| `Swatches.swift` | Workspaces, swatches, picking (pixels, loupe, markers), Swatch bar |
| `Transform.swift` | The prototype's quad geometry and modes, drawing into a quad, Transform handles and bar |
| `WorkspaceView.swift` | Workspace: tools, layers, Look and Grid bars, transform gestures, full screen, Share |
| `CanvasContent.swift` | The canvas's layers and grid, drawn for the screen and for Share; the export and share sheet |
| `CanvasGestures.swift` | Pan, pinch and twist with UIKit recognizers (SwiftUI's combined gesture hung) |
| `ColorStudy.swift` | Simplify and Highlight (the prototype's math, applied with a Core Image color cube), their bars |
| `ClassicPalettes.swift` | Zorn, Sargent, classical, triad, split primary, earth: roles filled from your paints (palettes.py) |
| `ColorPanel.swift` | The Color panel: swatch Details, and Paints & mixes (Mix from, Lighten with, recipes) |
| `Compare.swift` | Compare modes, which layers show, the Split line, Compare bar |
| `Crop.swift` | Crop math (same as the prototype), crop frame and handles, Crop bar |
