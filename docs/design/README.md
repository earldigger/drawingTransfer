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
| F | **Canvas fits clear of the UI by default.** It is sized to the space between the tool strip, layer bar, top bar and context bar, and keeps that size whether or not a bar is showing. | Pinch / two-finger drag still move it, but normally not needed. |
| G | **Full-screen mode** for working at the easel: all UI hidden, the canvas fills the screen. | Top-bar button to enter; faint exit button (fades) or four-finger tap to leave (Procreate convention). |
| H | **Layer bar collapses to a thin icon bar** (thumbnails only) on the right. | Expanded (names, blend · opacity) only while setting layers up. |
| I | **Opacity and blend mode live in the Look popover**, opacity first and largest. | Layer cards show them as a one-line summary only. |
| J | **Blue for active and primary controls** (active tool, selected segment, Done, slider fills, switches). Panels stay neutral gray. | Replaces the earlier one-accent-only rule. |
| K | **Portrait iPad: the same layout, rotated.** | Works because the layer bar collapses and full screen hides the UI. |

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
- **Layer bar** (right edge): collapsed by default to a thin icon bar of
  thumbnails; ‹ expands it to show name, eye and a blend · opacity summary.
  Tap a layer to select it, tap again to open its **Look** popover: opacity,
  blend mode (Normal, Multiply, Screen, Linear Light), levels, hue /
  saturation / colorize, invert, perspective. ＋ adds a layer from the camera
  or Photos.
- **Top bar**: back to Gallery, project name, the Transfer | Color switch,
  undo / redo, Full screen, Share.
- **Canvas**: neutral gray surround; gestures per decision C.
- **Chrome**: panels in neutral grays; blue for active and primary controls
  (decision J).

### Wireframes (done)

Figma page *2 · iPad screens*, column *Workspace · Transfer*, has four iPad frames, each with numbered
notes beside it:

1. **Transform** — tool strip with Transform active, canvas fitted clear of the
   UI with transform handles on the drawing, collapsed layer bar, context bar
   (Proportional / Free / Skew / Distort, Flip H / V, Fit, Cancel, **Done**).
2. **Look popover** — opened from the collapsed layer bar: Opacity (largest),
   blend mode, Levels (histogram + Black / Gamma / White), Hue / Saturation /
   Lightness, Colorize, Invert, Perspective → Edit corners.
3. **Layers expanded** — the layer bar with names and summaries.
4. **Full screen** — UI hidden, canvas fills the height, faint exit button.

Reusable components on that page (section *Components*): `icon/*` (19 line icons), **Tool button**
(Default / Active, icon swap), **Layer card** (Size Expanded / Collapsed ×
Selected; Name and Summary text properties).

Open questions:

1. The Look popover is tall (~615 pt) and covers the right edge of the canvas.
   Acceptable for quick changes; could be made draggable if it gets in the way.
2. Colorize needs its own hue / saturation sliders when on — not drawn yet.
3. Should a tap in full screen do anything (e.g. blink the drawing layer)? Off
   by default to avoid accidental changes.

## Camera (iPad) — wireframe plan

Figma page *2 · iPad screens*, column *Camera* (the Starter plan allows only
three pages, so screens share one page in columns).

1. **Capture** (drawn) — full-screen live view. The detected rectangle is
   outlined live; status and warnings (glare, too dark, angle too steep) sit on
   the image where the problem is. Right-edge column: Auto switch (shoot once
   the rectangle is steady ~1 s), 80 pt shutter, Photos library. Bottom:
   **Drawing | Canvas progress**, chosen before the shot because it decides what
   happens next. Default: Drawing if the project has none yet, otherwise
   Canvas progress.
2. **Adjust corners** (drawn) — frozen photo with the detected quad; outside
   is dimmed. 30 pt corner handles (44 pt hit area), Pencil or finger; a loupe
   with a crosshair sits above the corner being dragged. Side panel: live
   corrected preview with pixel size and ratio, Use as (Drawing / Canvas
   progress), Auto levels (on for drawings), Rotate 90°, Reset to detected,
   **Add layer** (blue). Retake / Cancel in the top bar. The four corners are
   the crop; no separate crop step. No rectangle found → corners start inset
   10 %.
3. **Layer added** — drawn in HTML (see below). A new drawing lands
   selected, at Multiply 60 %, fitted to the canvas, with Transform already
   active; toast "Drawing added — place it with Transform · Undo". A canvas
   progress photo fills the canvas exactly, lands at Normal 100 % under the
   drawing, hides the previous canvas photo, and offers "Compare with Oct 22".

Open questions:

1. Is Auto capture worth having? It helps only if the iPad is held still or
   on a stand aimed at the easel.
2. Auto levels for canvas progress: off by default? Brightening the painting
   helps line comparison but misstates its values.
3. Hide the older canvas photo automatically when a new one arrives?
4. Default look for a new drawing: is Multiply 60 % what you usually set
   first?

## Remaining iPad screens — HTML wireframes

Figma's Starter plan ran out of MCP calls, so the rest are in
[`screens/ipad.html`](screens/ipad.html): one self-contained page (open it in
any browser), each screen at 1180 × 820 with numbered notes beside it.

| # | Screen | Key points |
|---|---|---|
| 1 | Camera — Layer added | Drawing → Transform on; canvas photo → fills canvas, offers Compare. |
| 2 | Compare — Split | Overlay / Blink drawing / Blink A/B / Split in one control; A, B, swap; draggable line; *New photo* → Camera with Canvas progress chosen. |
| 3 | Compare — Blink A/B | Label shows which layer is up; speed 0.1–5 s; tap the canvas to pause. In full screen, **tap = pause / resume blink** (only while Compare is on). |
| 4 | Color — Pick, Highlight, Details | Tools: Pick, Simplify, Highlight, Grid. Loupe while picking. Swatch chips along the bottom with highlight range. One right-hand panel, tabs **Details \| Paints & mixes**, always shown in Color, so the Color canvas fits to its left. |
| 5 | Color — Simplify, Paints & mixes | Colors / Values / Value scale, steps, smoothing, value strip under the canvas. Mixes from a palette with ΔE; under 2 in blue. |
| 6 | Paint library | Full-screen sheet: Paints \| Palettes, medium list, table, detail; Import saved page, Add paint. |
| 7 | Gallery | Thumbnails at real proportions; New project, Open from Files, Settings. |
| 8 | New project | Name, size chips (8×10 – 36×48, Custom), in \| cm, orientation, to-scale preview; saved at once. |
| 9 | Share | Canvas view (full res, no UI), Swatch sheet (PDF), Project file; then the iOS share sheet. |
| 10 | Settings | Storage locations; defaults (units, new drawing look, auto levels, grid, blink speed); gestures cheat sheet. |

Open questions from these screens:

1. Show only the selected layer's swatches, or all of them?
2. Mix ratios (3 : 1 : 1.5): show them, or paint names only, given Mixbox
   treats every paint as equally strong?
3. Paint library on iPad: full editing, or mostly read-only with editing on
   the Mac?
4. Which canvas sizes do you actually use? Trim the chips to those.
5. Should the 302 pt Color panel collapse like the layer bar?

Not yet designed: iPhone (Gallery, Capture, Sketchbook transfer, Quick look)
and Mac (Workspace with docked panels, Add images, Paint library table).
