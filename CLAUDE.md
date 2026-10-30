# Canvas Transfer — notes for Claude sessions

Read this first. It holds the working agreements that aren't obvious from
the code. The owner has basic Python knowledge: explain plainly, challenge
assumptions, say how confident you are ("likely" / "guessing").

## What's here

- `canvastransfer/` — the Python/PySide6 **prototype** for the Mac (Transfer,
  Color Study, Paints). Tests in `tests/`.
- `ios/CanvasTransferTest/` — the **iPad test app** (SwiftUI, iPadOS 17).
  Not the real app: it tests camera, rectangle detection, Pencil/touch and
  color on the iPad. See its README.
- `docs/design/` — the design: names, decisions, workflow, and HTML
  wireframes for iPad, iPhone and Mac (`screens/*.html`). Use the names in
  its Names table (Canvas photo, Reference, Look, Crop, …).

## Branches and who works where

- Default branch: `claude/app-development-exploration-8b1z4w` (there is no
  `main`). Work is merged into it by pull request.
- **Xcode agent** (on the owner's Mac): Swift work on `ios-test-app`. Push
  after every commit, so work never sits only on the Mac.
- **Cloud sessions**: Python and design work on their own branch, started
  fresh from the default branch.
- Don't change `ios/` from a cloud session while the Xcode agent is active:
  hand it a prompt instead. Two agents on one branch caused diverged
  histories before.
- Merge, don't rebase, when combining someone else's work.

## Running the Python prototype (owner's Mac)

The project folder `~/dev/drawingTransfer` belongs to the Xcode agent. The
prototype runs from a second checkout (a git worktree) of the default branch:

```
cd ~/dev/drawingTransfer-python
source .venv/bin/activate
git fetch origin
git checkout --detach origin/claude/app-development-exploration-8b1z4w
pip install -r requirements.txt
python -m canvastransfer.main
```

Tests: `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/` (on Linux the
Qt system libraries libegl1, libgl1, libxkbcommon0, libfontconfig1 and
libdbus-1-3 are needed). Keep them passing.

## Color mixing — decisions and evidence

- **Personal use only for now.** Mixbox (CC BY-NC) and artistpigments.org
  data (CC BY-NC) are fine for the owner's own version. Licensing is dealt
  with if the app ever goes public; `km_mixing.py` (Kubelka-Munk, free) is
  the fallback for that.
- **Mixbox is the default model.** Tested against the owner's real paint
  (RAW photo, Oct 2026): Old Holland Old Delft Blue + white is clear blue
  (Mixbox ΔE 3.4; Kubelka-Munk goes violet, ΔE 12). Brown Ochre Deep +
  white: neither model is good on hue (the real tint is greyer).
- **Kubelka-Munk** matches spectral.js (shares squared × lightness), checked
  against the artistpigments.org Spectral.js mode. Kept for comparison.
- **Measured spectra aren't worth importing.** artistpigments.org only shows
  curves as images; read off the image, they changed tints by only ~ΔE 2
  versus the guessed curves (both paints tested).
- **Paint strength** (Edit Paint > Strength) is what fixes recipe amounts.
  Measured against Mixbox: Old Delft Blue ×3 (1:3 with white looks like
  the model's 1:1), Brown Ochre Deep ×1. Get more from the owner's tints:
  paint + white at a known ratio, RAW photo, compare at matching lightness.
- Possible next steps (not started): strength from a photo inside the app;
  replacing a paint's library color with one measured from the owner's own
  masstone.

## iPad app — open work

- **Flatten** (asked for, Oct 2026): render the visible layers as shown into
  a new layer so Pick/Simplify/Highlight read what you see; hide the
  originals; **Update** re-renders and refreshes its swatches. No masks,
  painting or merge-down: it isn't an image editor.
