# Canvas Transfer — app design

Design work for the iPhone / iPad / Mac app. The desktop Python prototype
in this repo is the working spec of what the app does; this folder records
how it should look and be organised.

**All screens are in [`screens/`](screens/)** — [`ipad.html`](screens/ipad.html), [`iphone.html`](screens/iphone.html), [`mac.html`](screens/mac.html) — in
workflow order, each with numbered notes; open them in any browser. The
earlier Figma file ([Canvas Transfer – iPad design](https://www.figma.com/design/AKfGx0W7u726iwbbJ7EGSL))
is no longer needed: its screens were rebuilt in the HTML with the current
names and decisions.

## Who and where

| Device | Priority | Used for |
|---|---|---|
| iPad | 1 | On a stand next to the easel. Takes the photos too. Sometimes sends a view to the desktop. |
| iPhone | 2 | Taking photos for the iPad or desktop. Sketchbook drawing at a cafe; color tools rarely. |
| Mac | 3 | Full resolution; finding images on the web, saving them, adding them to a project. |

## Workflow

1. **Add a canvas photo**: photograph the destination canvas.
2. **Adjust its perspective**: four corners, so it fills the canvas exactly.
3. **Add a reference** (a photo or a drawing) on top, at Multiply 60 %.
4. **Fit the reference** with Transform where it belongs. It doesn't always
   fill the canvas; it might be a small face in one corner.

Then, while painting: new canvas photos as the painting progresses, Compare,
Look adjustments, and the Color tools. Steps 1–4 get the biggest,
closest-to-hand controls.

## Names

The words the app uses on screen. Where an older note says
something else, these win.

| Name | Means | Not called |
|---|---|---|
| **Project** | One painting: its canvas size, layers, swatches. A `.ctproj` file. | document, file |
| **Canvas** | The real canvas you paint on, and its size in the project (16 × 20 in). | — |
| **Canvas photo** | A layer: a photo of your canvas, perspective-corrected to fill the canvas exactly. Starts at Normal 100 % and is never changed automatically; no auto levels. A project collects several over time (“Canvas · Oct 22”). | canvas progress, painting photo |
| **Reference** | A layer: the photo or drawing you transfer from. Starts at Multiply 60 % (white paper disappears), with auto levels; placed with Transform, at any size. | drawing, source, overlay |
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
| **Mix** | One or two paints plus a lightener, predicted to match a swatch. Each paint's share is a percentage (adding up to 100); a guide, not a recipe. | recipe |

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

**iPhone:** Gallery · New project · Camera (photo → corners → add to any project, or share) · Transfer workspace (sketchbook transfer is an ordinary project) · Layers & Look sheet · Compare · Color (mostly Simplify) · Paint library. “Quick look” is Full screen.

**Mac:** Gallery · Workspace (dockable panels, shortcuts, menus) · Add images (drag from a browser or Finder, paste, import) · Paint library & palettes (table view; saved-page import lives here).

## Workspace · Transfer (iPad, landscape 1180 × 820 pt)

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

### Screens

In `screens/ipad.html`: *Transfer — Transform*, *Look*, *Layer bar
expanded*, *Full screen*. The Transform and Look screens show the canvas
photo of a toned, still-empty canvas with a small reference placed in one
corner (workflow steps 1–4).

Open questions:

1. The Look popover is tall (~560 pt) and covers the right edge of the
   canvas. Fine for quick changes; could be made draggable.
2. Colorize needs its own hue / saturation sliders when on — not drawn yet.

## Camera (iPad)

1. **Capture** — full-screen live view. The detected rectangle is outlined
   live; warnings (glare, too dark, angle too steep) sit on the image where
   the problem is. Right edge: 80 pt shutter, Photos. Bottom: **Canvas |
   Reference**, chosen before the shot. Default: Canvas if the project has no
   canvas photo yet, then Reference if it has no reference yet, otherwise
   Canvas. No auto capture.
2. **Adjust corners** — the four corners are the crop; loupe while
   dragging; preview (no title); Use as; Auto levels (on for references,
   off for canvas photos); Rotate 90°; Reset to detected; **Add layer**.
3. **Layer added** — a reference lands on top at Multiply 60 % with
   Transform on. A canvas photo fills the canvas at Normal 100 % under the
   references; older canvas photos are not changed. Offers Compare.

## All iPad screens

[`screens/ipad.html`](screens/ipad.html): one self-contained page, each
screen at 1180 × 820 with numbered notes beside it, in workflow order.

| Screen | Key points |
|---|---|
| Gallery | Thumbnails at real proportions, grouped by month; New project, Open from Files, Settings. |
| New project | Name, size chips (8×10 – 36×48, Custom), in \| cm, orientation, preview; Create opens Camera with Canvas chosen. |
| Camera — Capture | Canvas \| Reference; live detection and warnings; shutter, Photos. |
| Camera — Adjust corners | Corners = crop, loupe, preview, Use as, Auto levels (references only), Add layer. |
| Camera — Layer added | Reference → Multiply 60 %, Transform on; canvas photo → Normal 100 %, offers Compare. |
| Transfer — Transform | Top bar, tool strip, view fitted clear of the UI, collapsed layer bar, Transform context bar. |
| Transfer — Look | Opacity first, blend, levels, hue / saturation, colorize, invert, perspective. No title. |
| Transfer — Layer bar expanded | Thumbnail, name, eye, blend · opacity summary; ＋ Layer. |
| Transfer — Full screen | Canvas only; faint exit button or four-finger tap. |
| Compare — Split | Overlay / Blink reference / Blink A/B / Split in one control; A, B, swap; draggable vertical line; *New photo* → Camera with Canvas chosen. |
| Compare — Blink A/B | Label shows which layer is up; speed 0.1–5 s; tap the canvas to pause. In full screen, **tap = pause / resume blink** (only while Compare is on). |
| Color — Pick, Highlight, Details | Tools: Pick, Simplify, Highlight, Grid. Loupe while picking. Swatch chips along the bottom with highlight range. One right-hand panel, tabs **Details \| Paints & mixes**, collapsible; the swatch bar shows all swatches. |
| Color — Simplify, Paints & mixes | Colors / Values / Value scale, steps, smoothing, value strip under the canvas. Mixes from a palette: 64 pt chip (yours \| mix, halves touching), one line per paint led by its % of the mix, then ΔE and how close (very close / close / noticeably different / far off; blue under 2). Percentages are a guide. |
| Paint library | Full-screen sheet: Paints \| Palettes, medium list, table, detail with hex; Import saved page, Add paint. Full-featured on every device. |
| Edit paint | Medium (move between oil, watercolor…), name, brand, series, pigments, color as hex or L*a*b*, opacity, lightfastness, drying, source; favorite, use in mixes, stand-in. |
| Share | Canvas view (full res, no UI), Swatch sheet (PDF), Project file; then the iOS share sheet. |
| Settings | Storage locations; defaults (units, new reference look, auto levels, grid, blink speed); gestures cheat sheet. |

Decided from the first review: older canvas photos are never hidden or
changed automatically; Split is vertical only; the Color panel collapses and
the swatch bar shows all swatches; mix amounts stay, as percentages and a guide; the paint
library is full-featured on every device, with hex in the detail; the
Gallery groups by time; the canvas-size chips stay as they are.

## iPhone screens

[`screens/iphone.html`](screens/iphone.html): the same projects and workflow
on a phone held upright (393 × 852 pt). A sketchbook is just a project whose
canvas is the sketchbook page.

| Screen | Key points |
|---|---|
| Gallery | Large title, two columns, grouped by month; Open from Files, Settings, ＋. |
| New project | Bottom sheet; same three choices; Create opens Camera with Canvas chosen. |
| Camera — Capture | Project is a menu (shoot for any project, or New project…); Canvas \| Reference above the shutter; Photos. |
| Camera — Adjust corners | Bigger handles, loupe beside the corner; compact sheet; **Add layer** or **Share photo instead**. |
| Transfer — Transform | Top bar: back, undo, Transfer \| Color, Full screen, Share. One-row context bar (mode menu, ⋯ for flips and Fit). Bottom toolbar replaces the tool strip and adds **Layers**. |
| Transfer — Layers & Look | One half-height sheet: layer row on top, the selected layer's Look below (opacity first, blend; Levels and Hue / Saturation one level down). |
| Transfer — Full screen | Canvas as wide as the phone; replaces the separate “Quick look”. |
| Compare — Split | A / B chosen from the labels on the canvas; modes in one row. |
| Color — Simplify | Value check for sketchbook shading; Swatches sheet holds Details and Paints & mixes. |
| Color — Paints & mixes | Swatches sheet (opens tall): every swatch in a row, Details \| Paints & mixes, Mix from, Lighten with. Each mix: a 76 pt chip (yours \| mix, halves touching so the shift shows), one line per paint led by its %, then ΔE and how close. |
| Paint library | iOS list with search, Paints \| Palettes, medium chips. |
| Edit paint | Grouped form, same fields as iPad. |

Not drawn for iPhone (same content as iPad, in a sheet or list): Look's
Levels and Hue / Saturation pages, Compare — Blink, Color — Pick, Share,
Settings.

## Mac screens

[`screens/mac.html`](screens/mac.html): the same projects in a Mac window
(1280 × 800 plus the menu bar). Panels are docked, every action is in a menu,
the common ones have keys.

| Screen | Key points |
|---|---|
| Gallery | Window with search, Open… ⌘O, New Project ⌘N; grouped by month; projects open in their own windows. |
| Transfer workspace | Docked tool column (key on each tool: T, P, G, C) with **Add** instead of Camera; docked inspector with Layers on top and the selected layer's Look always open below; context bar with ↩ Done / esc Cancel. |
| Menus & keys | File, Edit, Layer, View, Window. Number keys set opacity (1 = 10 % … 0 = 100 %); ⌥⇧N / M / S / J blend modes; ⇥ hides panels; F full screen. |
| Add images | Drag from Safari, Finder or Photos: drop on **Reference** (Multiply 60 %, Transform, no corner step) or **Canvas photo** (Adjust corners). ⌘V pastes a reference; Take Photo with iPhone (Continuity Camera). |
| Color workspace | Swatches docked in the inspector, Details \| Paints & mixes as on the other devices; Pick shows the color under the pointer live. |
| Paint library | Own window ⇧⌘L: sidebar (media, your palettes, classic palettes), sortable table, inspector that is the editor (no separate Edit sheet). |
| Settings | ⌘, — General, Storage, Defaults (shown), Keys. |
