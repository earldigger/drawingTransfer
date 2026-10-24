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

## Workflow

1. **Add a canvas photo**: photograph the destination canvas.
2. **Adjust its perspective**: four corners, so it fills the canvas exactly.
3. **Add a reference** (a photo or a drawing) on top, at 60 % opacity.
4. **Fit the reference** with Transform where it belongs. It doesn't always
   fill the canvas; it might be a small face in one corner.

Then, while painting: new canvas photos as the painting progresses, Compare,
Look adjustments, and the Color tools. Steps 1–4 get the biggest,
closest-to-hand controls.

## Names

The words the app uses on screen. Where an older Figma frame or note says
something else, these win.

| Name | Means | Not called |
|---|---|---|
| **Project** | One painting: its canvas size, layers, swatches. A `.ctproj` file. | document, file |
| **Canvas** | The real canvas you paint on, and its size in the project (16 × 20 in). | — |
| **Canvas photo** | A layer: a photo of your canvas, perspective-corrected to fill the canvas exactly. Opacity stays 100 % unless you change it. A project collects several over time (“Canvas · Oct 22”). | canvas progress, painting photo |
| **Reference** | A layer: the photo or drawing you transfer from. Added at 60 % opacity and placed with Transform, at any size. | drawing, source, overlay |
| **Layer** | A canvas photo or a reference. Listed in the layer bar. | — |
| **Layer bar** | The strip of layer thumbnails on the right; collapses to icons. | layer strip, layers panel |
| **Look** | The popover for one layer: opacity, blend mode, levels, hue / saturation, colorize, invert, perspective. No title; it points at its layer. | Look · Drawing, adjustments |
| **Camera** | Taking a photo for a layer: Capture → Adjust corners → Add layer. You choose **Canvas \| Reference** before the shot. | — |
| **Transfer / Color** | The two workspaces, switched in the top bar. | modes, tabs |
| **Tool** | One item of the left tool strip (Camera, Transform, Perspective, Grid, Compare; in Color: Pick, Simplify, Highlight, Grid). Its options appear in the **context bar** at the bottom. | — |
| **Compare** | Viewing two layers against each other: Overlay, Blink reference, Blink A / B, Split. | — |
| **Full screen** | Canvas only, all UI hidden. | presentation mode |
| **Swatch** | A color picked from a layer, numbered. | sample, chip |
| **Paint** | A tube in your paint library (name, brand, pigments, color, …). | color |
| **Palette** | A named set of paints (yours, or a classic one like Zorn). | — |
| **Mix** | One or two paints plus a lightener, predicted to match a swatch. Amounts are a guide, not a recipe. | recipe |

Watch for: *canvas* now means the real canvas; the area of the screen it is
shown in is just “the view”.

## Decisions

| | Decision | Notes |
|---|---|---|
| A | **iCloud Drive for everything**: projects and the paint library | Projects are folder documents (`.ctproj`); iCloud Drive keeps them in sync on iPhone and iPad. The prototype now defaults to `iCloud Drive/Canvas Transfer/` (Dropbox only if iCloud Drive is off). |
| B | **Two workspaces: Transfer and Color**, one switch in the top bar | Fewer tools on screen at the easel. Same layers in both. |
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
4. Camera — photograph the canvas or a reference; rectangle found automatically; adjust 4 corners; choose *Canvas* or *Reference*; becomes a layer.
5. Compare — overlay, blink reference, blink A/B, split with a draggable vertical line; one tap for a new canvas photo.
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
│ #  │          (canvas photo + reference at 60 %)               │ ─────●─ │  opacity slider,
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
   UI with transform handles on the reference, collapsed layer bar, context bar
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
3. ~~Tap in full screen~~ — decided: pauses / resumes Blink while Compare is
   on; does nothing otherwise.

## Camera (iPad) — wireframe plan

Figma page *2 · iPad screens*, column *Camera* (the Starter plan allows only
three pages, so screens share one page in columns).

1. **Capture** (drawn) — full-screen live view. The detected rectangle is
   outlined live; status and warnings (glare, too dark, angle too steep) sit on
   the image where the problem is. Right-edge column: Auto switch (shoot once
   the rectangle is steady ~1 s), 80 pt shutter, Photos library. Bottom:
   **Canvas | Reference**, chosen before the shot because it decides what
   happens next. Default: Canvas if the project has no canvas photo yet, then
   Reference if it has no reference yet, otherwise Canvas.
2. **Adjust corners** (drawn) — frozen photo with the detected quad; outside
   is dimmed. 30 pt corner handles (44 pt hit area), Pencil or finger; a loupe
   with a crosshair sits above the corner being dragged. Side panel: live
   corrected preview (no title) with pixel size and ratio, Use as (Canvas /
   Reference), Auto levels (on for references), Rotate 90°, Reset to detected,
   **Add layer** (blue). Retake / Cancel in the top bar. The four corners are
   the crop; no separate crop step. No rectangle found → corners start inset
   10 %.
3. **Layer added** — drawn in HTML (see below). A new reference lands on
   top, selected, at Normal 60 %, fitted inside the canvas, with Transform
   already active; toast "Reference added — place it with Transform · Undo".
   A canvas photo fills the canvas exactly and lands at Normal 100 % just
   under the references. Older canvas photos are **not** hidden or changed.
   It offers "Compare with Oct 22".

Open questions:

1. Is Auto capture worth having? It helps only if the iPad is held still or
   on a stand aimed at the easel.
2. Auto levels for canvas photos: off by default (proposed)? Brightening the
   painting helps line comparison but misstates its values.

The Figma frames still show the old names (*Drawing / Canvas progress*,
*Look · Drawing*, *Result*); the names table above wins, and the HTML
screens use the new ones.

## Remaining iPad screens — HTML wireframes

Figma's Starter plan ran out of MCP calls, so the rest are in
[`screens/ipad.html`](screens/ipad.html): one self-contained page (open it in
any browser), each screen at 1180 × 820 with numbered notes beside it.

| # | Screen | Key points |
|---|---|---|
| 1 | Camera — Layer added | Reference → Normal 60 %, Transform on; canvas photo → fills canvas, offers Compare. |
| 2 | Compare — Split | Overlay / Blink reference / Blink A/B / Split in one control; A, B, swap; draggable vertical line; *New photo* → Camera with Canvas chosen. |
| 3 | Compare — Blink A/B | Label shows which layer is up; speed 0.1–5 s; tap the canvas to pause. In full screen, **tap = pause / resume blink** (only while Compare is on). |
| 4 | Color — Pick, Highlight, Details | Tools: Pick, Simplify, Highlight, Grid. Loupe while picking. Swatch chips along the bottom with highlight range. One right-hand panel, tabs **Details \| Paints & mixes**, collapsible; the swatch bar shows all swatches. |
| 5 | Color — Simplify, Paints & mixes | Colors / Values / Value scale, steps, smoothing, value strip under the canvas. Mixes from a palette with ΔE (under 2 in blue) and ratios as a guide. |
| 6 | Paint library | Full-screen sheet: Paints \| Palettes, medium list, table, detail with hex; Import saved page, Add paint. Full-featured on every device. |
| 7 | Edit paint | Medium (move between oil, watercolor…), name, brand, series, pigments, color as hex or L*a*b*, opacity, lightfastness, drying, source; favorite, use in mixes, stand-in. |
| 8 | Gallery | Thumbnails at real proportions, grouped by time; New project, Open from Files, Settings. |
| 9 | New project | Name, size chips (8×10 – 36×48, Custom), in \| cm, orientation, to-scale preview; saved at once; Create opens Camera with Canvas chosen. |
| 10 | Share | Canvas view (full res, no UI), Swatch sheet (PDF), Project file; then the iOS share sheet. |
| 11 | Settings | Storage locations; defaults (units, new reference look, auto levels, grid, blink speed); gestures cheat sheet. |

Decided from the first review: older canvas photos are never hidden or
changed automatically; Split is vertical only; the Color panel collapses and
the swatch bar shows all swatches; mix ratios stay, as a guide; the paint
library is full-featured on every device, with hex in the detail; the
Gallery groups by time; the canvas-size chips stay as they are.

Not yet designed: iPhone (Gallery, Capture, Sketchbook transfer, Quick look)
and Mac (Workspace with docked panels, Add images, Paint library table).
