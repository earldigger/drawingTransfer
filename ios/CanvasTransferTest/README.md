# Canvas Transfer — iPad test app

A small iPad app that tests the three things the Python prototype can't:

1. **Live rectangle detection** — Apple Vision outlines the canvas or paper in
   the camera view, and finds the corners again on the photo you take.
2. **Pencil and touch** — dragging corners with a loupe, and moving, pinching
   and twisting a reference into place.
3. **Color on the iPad** — images at Multiply 60 % (with auto levels),
   stacked as layers, opacity, and full screen.

It is not the app: there are no projects or iCloud, and paints can't be
edited here (that's the prototype's job). The current session is saved on the iPad as you work and reopens at
launch; deleting the app deletes it. Names and defaults follow `docs/design/README.md`.

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

- **Camera** (left strip): point at the canvas on the easel. Does the blue
  outline find it — in studio light, at an angle, with a busy background?
  Note when it fails.
- Take the photo: are the corners already right? Drag them — is the loupe
  where you need it, with finger and with Pencil?
- **Whole photo** puts the corners at the photo's edges; **Detected outline**
  brings back what Vision found. **Find rectangle** (on the camera, and in
  Adjust corners) turns detection off; it's remembered.
- **Add layer**: every image lands at Multiply 60 % with auto levels and
  Transform on: one finger moves it, pinch scales, twist rotates.
- **Crop** (bottom bar): drag the corners or edge middles, or inside the frame
  to slide it; what's cut off shows faintly. Free, Original or Square; Reset;
  Cancel or Done. The crop moves, scales and turns with the image, and Crop
  again brings back what you cut.
- **Color** (top bar): Pick is on; touch the canvas for a loupe on the
  selected layer and lift to add a numbered swatch. Two fingers pan and zoom.
  The Swatch bar shows hex, RGB and value; long-press a chip to delete it.
- **Flatten** (bottom of the layer bar): the visible layers exactly as shown
  (opacity, blend, Look, crop, transform) become one new layer, "Flattened 1",
  on top at Normal 100 %, filling the canvas; the layers in it are hidden,
  not deleted. Pick, Simplify and Highlight on it read what you see. In Color,
  a layer that isn't at Normal 100 % shows a hint to flatten.
- **Update** (layer bar, or long-press a flattened layer): show the layers you
  want and Update. The flattened layer is hidden, rendered again from what's
  visible, and its swatches are read again at the same spots.
- **Details | Paints & mixes** (Color, opens when you select a swatch):
  hex, RGB, Lab, value, warm or cool, complement, and Mixbox tints, shades
  and tones; then Mix from (a palette or all your paints of a medium) and
  Lighten with (a white, water or nothing), and the best one-paint and
  two-paint recipes with ΔE. Mix from also offers the classic palettes (Zorn,
  Sargent, …) filled from your paints, and Favorites only. Your paints come
  from the prototype's paints.json; **Import paints…** loads a newer one.
- **Measure strength…** (Paints & mixes): mix a paint with white at a known
  ratio (say 1 : 3), photograph the tint next to a dab of the same white in
  even light, add it as a layer, and pick a swatch on each. The white cancels
  the photo's exposure and cast; the strength is where Mixbox's tint has your
  lightness, with how far the hue is off. Strengths measured here are used in
  the iPad's mixes and listed to copy into the prototype by hand.
- **Share swatch sheet (PDF)** (top right): the canvas with its numbered
  swatches, and each swatch's numbers and best mixes, to print or keep at the easel.
- **Simplify** (Color): Colors, Values or Value scale, 2–12, smoothing; the
  colors found with their shares. Pick reads the flat color you see.
  **Highlight**: each swatch's range in its own bright color over gray.
- **Transform**: a bar with Proportional, Free, Skew and Distort for the
  corner and edge handles, Flip H / V, Fit, Cancel and Done. Fingers move,
  pinch and twist in every mode. Placement is four corners, as in the prototype.
- **Undo / redo**: the top-bar buttons, a two-finger tap to undo, a
  three-finger tap to redo, or ⌘Z / ⇧⌘Z. A gesture, an opacity drag or a
  whole crop is one step; selecting a layer isn't.
- **Adjust** (bottom bar): invert, levels, hue / saturation or colorize,
  lightness, as in the prototype; live, saved and undoable. Blend has Normal,
  Multiply and Screen.
- **Compare** (left strip): Blink A (A fades in and out), Blink A / B (a
  crossfade), or Split with a draggable line; A and B, swap, speed, pause. The layer bar numbers the layers and
  marks A and B.
- **Layers** (right): ‹ expands the bar to numbers, eyes and blend ·
  opacity. Long-press a layer to move it up or down, to the front or back,
  duplicate, hide or delete it. The Look bar's **⋯** has Fit, Flip
  horizontal / vertical, and **Edit corners…**, which reopens Adjust corners
  on the original photo (kept since this build) and keeps the placement.
- **Grid** (left strip): rows and columns, Square cells, color and opacity.
  It's saved with the session but isn't an undo step.
- **Share** (top right): the canvas as a full-resolution JPEG, with or
  without the grid, through the share sheet (AirDrop to the Mac, Files).
- Compare the colors with the Mac prototype and with the real canvas.
- **Full screen** (top right) for working at the easel; the faint button
  top-left comes back.
- Photos (left strip) adds an image from your library.

## Files

| File | What it does |
|---|---|
| `CanvasTransferTestApp.swift` | App entry |
| `Autosave.swift` | Saves the session (session.json and a PNG per layer) and opens it at launch |
| `History.swift` | Undo and redo: a step per settled change, holds for gestures, drags and crops |
| `Flatten.swift` | Flatten and Update: the visible layers rendered into one layer, swatches read again |
| `Look.swift` | Adjustments (prototype's order and ranges) with Core Image; the Adjust popover |
| `Mixbox.swift`, `mixbox_lut.bin` | Mixbox 2.0 ported from pymixbox (CC BY-NC 4.0, personal use) and its lookup table |
| `Mixing.swift` | Lab D50, CIEDE2000, and the recipe search, as in the prototype's mixing.py |
| `Model.swift` | Layer (look, placement), the session, canvas sizes |
| `ImageOps.swift` | Upright photos, perspective correction, auto levels, rectangle detection |
| `Camera.swift` | Live camera with detection overlay; Capture screen |
| `CornersScreen.swift` | Adjust corners (handles, loupe); the capture flow |
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
