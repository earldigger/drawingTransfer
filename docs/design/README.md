# Canvas Transfer — app design

Design work for the iPhone / iPad / Mac app. The desktop Python prototype
in this repo is the working spec of what the app does; this folder records
how it should look and be organised.

Figma file: [Canvas Transfer – iPad design](https://www.figma.com/design/AKfGx0W7u726iwbbJ7EGSL)
(page *1 · Screen map*).

## Who and where

| Device | Priority | Used for |
|---|---|---|
| iPad | 1 | On a stand next to the easel. Takes the photos too. Sometimes sends a view to the desktop. |
| iPhone | 2 | Taking photos for the iPad or desktop. Sketchbook drawing at a cafe; color tools rarely. |
| Mac | 3 | Full resolution; finding images on the web, saving them, adding them to a project. |

**Most-used actions (in order):**
1. Take photos and adjust them (perspective, crop, levels).
2. Transform them onto the canvas.
3. Set each layer's look and opacity (blend, levels, invert) until the overlay
   shows how the drawing relates to the painting.

These get the biggest, closest-to-hand controls.

## Decisions

| | Decision | Notes |
|---|---|---|
| A | **iCloud Drive for everything**: projects and the paint library | Projects are folder documents (`.ctproj`); iCloud Drive keeps them in sync on iPhone and iPad. The prototype now defaults to `iCloud Drive/Canvas Transfer/` (Dropbox only if iCloud Drive is off). |
| B | **Two workspaces: Transfer and Color**, one switch in the top bar | Fewer tools on screen at the easel. Same canvas and layers in both. |
| C | **Pencil and touch both** pick colors and drag handles. **Zoom and pan as in Procreate**: pinch to zoom and rotate, two-finger drag to pan, quick pinch to fit. | Two-finger tap = undo, three-finger tap = redo (Procreate convention). |
| D | **Share button**: exports the composited canvas at full resolution, without panels, via the share sheet (AirDrop to the Mac, Messages, Files). | Replaces taking screenshots. Also: share a swatch sheet. |
| E | Panels float over a full-screen canvas, as in **Procreate and Fresco**. | No permanent sidebar. |

## Screen map

**iPad**
1. Gallery — recent projects as thumbnail cards, New, Open from Files.
2. New project — name, canvas size (presets 8×10 to 36×48, custom; in/cm), orientation; saved at once.
3. Workspace · Transfer — see below.
4. Camera — photograph the drawing or canvas; rectangle found automatically; adjust 4 corners; choose *Drawing* or *Canvas progress*; becomes a layer.
5. Compare — overlay, blink drawing, blink A/B, split with a draggable line; one tap for a new progress photo.
6. Workspace · Color — Pick, Simplify, Highlight; floating Swatches, Swatch details, Paints & mixes panels.
7. Paint library — full-screen sheet: paints by medium, palettes, edit, import a saved artistpigments page.
8. Share — export view or swatch sheet.
9. Settings — projects folder, paint library location, units, grid defaults.

**iPhone:** Gallery · Capture (photo → corners → add to a project or share) · Sketchbook transfer (reference over the sketchbook photo, grid, transform, opacity, value simplify) · Quick look.

**Mac:** Gallery · Workspace (dockable panels, shortcuts, menus) · Add images (drag from a browser or Finder, paste, import) · Paint library & palettes (table view; saved-page import lives here).

## Workspace · Transfer (iPad, landscape 1180 × 820 pt) — wireframe plan

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ‹ Gallery   Portrait of Ana        [ Transfer | Color ]     ↶  ↷   ⇪     │  top bar, 52 pt
├────┬───────────────────────────────────────────────────────────┬─────────┤
│ 📷 │                                                           │ ▣ 100%  │  layer strip,
│ ⤧  │                                                           │ ─●───── │  ~150 pt wide:
│ ⬚  │                  full-screen canvas                       │ ▣  60%  │  thumbnail,
│ #  │          (photo of canvas + drawing overlay)              │ ─────●─ │  opacity slider,
│ ◐  │                                                           │ ▣  45%  │  blend mode
│    │                                                           │  ＋     │
├────┘                                                           └─────────┤
│              contextual bar for the active tool (appears when needed)    │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Left tool strip** (44 pt targets, top to bottom): Camera, Transform,
  Perspective, Grid, Compare. The active tool shows its options in a bar at the
  bottom (Transform: Proportional / Free / Skew / Distort, Flip H / V, Fit,
  Done / Cancel).
- **Layer strip** (right edge, always visible): each layer is a thumbnail with
  its opacity slider and blend mode (Normal, Multiply, Screen, Linear Light)
  directly under it; eye toggle; tap a layer to select it, tap again to open
  its **Look** popover (levels, hue / saturation / colorize, invert,
  perspective). ＋ adds a layer from the camera or Photos. The strip collapses
  to thumbnails only with a swipe.
- **Top bar**: back to Gallery, project name, the Transfer | Color switch,
  undo / redo, Share.
- **Canvas**: neutral gray surround; gestures per decision C.
- **Neutral chrome**: panels in neutral grays, no colored accents near the
  image (colored UI next to the image changes how its colors look). One accent
  color only for the selection and active tool.

Next: wireframes of this screen, then Camera, Compare, Color workspace and Gallery.
