import PhotosUI
import SwiftUI
import UIKit

/// One photo on its way in, from Camera (`picked == nil`) or Photos.
struct Capture: Identifiable {
    let id = UUID()
    let picked: UIImage?
}

/// Transfer workspace, cut down to what this test needs: tools on the left,
/// layers on the right, the selected layer's look at the bottom, and the
/// canvas fitted between them.
struct WorkspaceView: View {
    var projectName = ""
    var onGallery: () -> Void = {}

    @Environment(TransferSession.self) private var session
    @Environment(History.self) private var history

    @State private var capture: Capture? = nil
    @State private var showPhotos = false
    @State private var photoItem: PhotosPickerItem? = nil
    @State private var transformOn = false
    @State private var transformMode = TransformMode.proportional
    @State private var transformStart: (id: UUID, quad: [CGPoint])? = nil  // for Cancel
    @State private var fullScreen = false
    @State private var viewScale: CGFloat = 1
    @State private var viewOffset: CGSize = .zero
    // While cropping: which layer, its crop before (for Cancel), and whether
    // Transform was on (it comes back after Done).
    @State private var cropping: (id: UUID, before: CGRect, wasTransforming: Bool)? = nil
    @State private var cropShape: CropShape = .free
    @State private var gridBarShown = false
    @State private var compare: CompareState? = nil  // nil = not comparing
    @State private var blinkClock = BlinkClock()  // Compare: where the blink is in its fade
    @State private var exporting = false  // rendering the image to share
    @State private var shareFile: ShareFile? = nil
    @State private var shareFailed = false
    @State private var editingCorners: CornerEdit? = nil
    @State private var layerBarExpanded = false  // names, eye, blend · opacity; collapsed by default (decision H)
    @State private var colorBarShown = false  // the color tool: its bar, the swatch panel and markers show
    @State private var swatchesOn = false  // its Eyedropper: one finger picks
    @State private var sampleSize = SampleSize.small
    @State private var selectedSwatchID: UUID? = nil
    @State private var probe: (pick: PickProbe, screen: CGPoint)? = nil  // while a finger is picking
    @State private var colorView = ColorView.normal  // Color: Simplify or Highlight the selected layer
    @State private var simplifySettings = SimplifySettings()
    @State private var highlightSettings = HighlightSettings()
    @State private var study: StudyResult? = nil  // the selected layer, simplified or highlighted
    @State private var studyWorking = false
    @State private var colorPanelOpen = true  // Details | Paints & mixes for the selected swatch
    @State private var paintLibraryOpen = false
    @State private var layersSheet = false  // the phone's layer list
    @State private var toolPopup: ToolPopup? = nil  // the phone's + or Transform / Crop choices
    @AppStorage("studyMarkersShown") private var studyMarkersShown = true  // swatch markers in Simplify and Highlight

    var body: some View {
        GeometryReader { geo in
            // Room for the bars, so the canvas sits clear of them (decision F). On the
            // phone: the top bar, and below, the stacked bar and the tool row.
            let margins = fullScreen ? EdgeInsets()
                : Theme.isPhone ? EdgeInsets(top: 60, leading: 8, bottom: 236, trailing: 8)
                : EdgeInsets(top: 68, leading: 24, bottom: 84, trailing: 96)
            let area = CGSize(width: geo.size.width - margins.leading - margins.trailing,
                              height: geo.size.height - margins.top - margins.bottom)
            let fitted = fitRect(session.canvasSize, in: area, margin: fullScreen ? 0 : 12)
            let rect = fitted.offsetBy(dx: margins.leading, dy: margins.top)
            ZStack {
                (fullScreen ? Color.black : Theme.canvasSurround).ignoresSafeArea()
                // Under the canvas, which lets touches through except on crop handles.
                CanvasGestureView(handlers: canvasGestures(canvas: rect.size, at: rect),
                                  picking: swatchesOn && !fullScreen)
                canvas(size: rect.size)
                    .scaleEffect(viewScale)
                    .offset(viewOffset)
                    .position(x: rect.midX, y: rect.midY)
                if fullScreen {
                    exitFullScreenButton
                } else {
                    chrome
                }
                if let probe {
                    Loupe(probe: probe.pick, sample: sampleSize)
                        .position(x: probe.screen.x, y: max(probe.screen.y - 120, 100))  // above the finger
                }
                if exporting {
                    ProgressView("Preparing image…")
                        .padding(24)
                        .themedBar()
                }
            }
        }
        .themed()
        .statusBarHidden(fullScreen)
        .sheet(item: $shareFile) { file in
            ShareSheet(items: [file.url]) { shareFile = nil }
        }
        .alert("Couldn't make the image", isPresented: $shareFailed) {
            Button("OK", role: .cancel) {}
        }
        .fullScreenCover(item: $capture) { c in
            CaptureFlow(canvasAspect: session.canvasAspect, picked: c.picked) { layer in
                capture = nil
                if let layer {
                    session.add(layer)
                    endTools()
                    transformOn = true  // place a new image straight away
                }
            }
        }
        .fullScreenCover(item: $editingCorners) { edit in
            if let source = edit.layer.source {
                CornersScreen(image: source, detected: edit.detected, notFoundInset: 0, start: edit.layer.corners,
                              addTitle: "Done", onAdd: { corners in
                                  edit.layer.applyCorners(corners, canvasAspect: session.canvasAspect)  // one undo step
                                  editingCorners = nil
                              }, onRetake: nil, onCancel: { editingCorners = nil })
            }
        }
        .fullScreenCover(isPresented: $paintLibraryOpen) {
            PaintLibraryView { paintLibraryOpen = false }
        }
        .sheet(isPresented: $layersSheet) {
            // The phone's layers: the iPad's layer bar, expanded, in a sheet.
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Layers").font(.title3.weight(.semibold))
                    layerBar.frame(maxWidth: .infinity, alignment: .trailing)
                }
                .padding(20)
            }
            .presentationDetents([.medium, .large])
            .presentationBackground(Theme.surface)
            .themed()
            .onAppear { layerBarExpanded = true }
        }
        .photosPicker(isPresented: $showPhotos, selection: $photoItem, matching: .images)
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            Task {
                if let data = try? await item.loadTransferable(type: Data.self), let image = UIImage(data: data) {
                    capture = Capture(picked: image)
                }
                photoItem = nil
            }
        }
        .onChange(of: session.selectedID) { _, id in
            if let cropping, cropping.id != id { finishCrop(keep: true) }  // another layer: keep this crop
            if transformOn { noteTransformStart() }
        }
        .onChange(of: selectedSwatchID) { _, id in
            // Choosing a swatch opens its panel again, on the layer it belongs to.
            guard let id, let swatch = session.swatches.first(where: { $0.id == id }) else { return }
            colorPanelOpen = true
            if session.layers.contains(where: { $0.id == swatch.layerID }) { session.selectedID = swatch.layerID }
        }
        .onChange(of: transformOn) { _, on in
            if on { noteTransformStart() } else { transformStart = nil }
        }
        // Simplify or Highlight again when what they depend on changes; a
        // moving slider settles first.
        .task(id: studyKey) {
            guard studyKey != nil, let layer = session.selected else {
                study = nil
                studyWorking = false
                return
            }
            studyWorking = true
            try? await Task.sleep(for: .milliseconds(120))
            guard !Task.isCancelled else { return }
            let source = layer.shownImage, view = colorView, simplify = simplifySettings
            let tolerance = highlightSettings.tolerance, swatches = highlightSwatches
            let result = await Task.detached(priority: .userInitiated) { () -> (UIImage, ColorStudy.Simplified?)? in
                switch view {
                case .simplify:
                    return ColorStudy.simplify(source, count: simplify.count, smoothing: simplify.smoothing, mode: simplify.mode)
                        .map { ($0.image, $0) }
                case .highlight:
                    return ColorStudy.highlight(source, swatches: swatches, tolerance: tolerance).map { ($0, nil) }
                case .normal:
                    return nil
                }
            }.value
            guard !Task.isCancelled else { return }
            studyWorking = false
            study = result.map { StudyResult(layerID: layer.id, view: view, image: $0.0, simplified: $0.1,
                                             pixels: PixelBuffer($0.0)) }
        }
        .onChange(of: compare?.paused) { _, paused in blinkClock.setPaused(paused ?? false) }
        .onChange(of: compare?.mode) { blinkClock.restart() }  // each mode starts on A
    }

    // MARK: tools

    /// The Eyedropper, Simplify or Highlight is on: colors are read from the selected layer.
    private var colorToolOn: Bool { swatchesOn || colorView != .normal }

    /// Turns every tool off, so the one being turned on is the only one
    /// (Grid on, then Transform: Grid goes off).
    private func endTools() {
        finishCrop(keep: true)
        transformOn = false
        gridBarShown = false
        compare = nil
        toolPopup = nil
        colorBarShown = false
        swatchesOn = false
        colorView = .normal
        probe = nil
    }

    // MARK: crop

    private func startCrop(_ layer: Layer) {
        compare = nil
        cropping = (layer.id, layer.crop, transformOn)
        cropShape = .free
        transformOn = false  // one finger and pinch move the view while cropping
        history.hold("crop")  // the whole crop, to Done, is one undo step
    }

    private func finishCrop(keep: Bool) {
        guard let c = cropping else { return }
        if !keep, let layer = session.layers.first(where: { $0.id == c.id }) { layer.crop = c.before }
        transformOn = c.wasTransforming
        cropping = nil
        history.release("crop")
    }

    /// Opens Adjust corners on the layer's original photo, where it left off.
    private func editCorners(_ layer: Layer) {
        guard let source = layer.source else { return }
        finishCrop(keep: true)
        compare = nil
        editingCorners = CornerEdit(layer: layer, detected: ImageOps.detectRectangle(in: source))
    }

    // MARK: transform

    /// Where the layer was when Transform came on, for Cancel.
    private func noteTransformStart() {
        transformStart = session.selected.map { ($0.id, $0.quad) }
    }

    /// Puts the layer back where it was when Transform came on.
    private func cancelTransform() {
        if let start = transformStart, let layer = session.layers.first(where: { $0.id == start.id }) {
            layer.quad = start.quad
        }
        transformOn = false
    }

    /// Off while cropping, which has its own Cancel.
    private var canUndo: Bool { cropping == nil && history.canUndo }
    private var canRedo: Bool { cropping == nil && history.canRedo }

    // MARK: canvas

    private func canvas(size: CGSize) -> some View {
        canvasContent(size: size)
        .allowsHitTesting(false)  // touches go to the gesture view underneath
        .overlay {
            if let cropping, let layer = session.selected, layer.id == cropping.id {
                CropFrame(layer: layer, canvas: size, shape: cropShape)
            } else if compare?.mode == .split {
                SplitHandle(split: Binding(get: { compare?.split ?? 0.5 }, set: { compare?.split = $0 }), canvas: size)
            } else if transformOn, let layer = session.selected {
                TransformHandles(layer: layer, canvas: size, mode: transformMode,
                                 onBegin: { history.hold("handle") },  // one drag, one step
                                 onEnd: { history.release("handle") })
            }
        }
        .overlay {
            // While the color tool is open, unless hidden to see the colors alone.
            if colorBarShown && studyMarkersShown {
                SwatchMarkers(swatches: session.swatches, layers: session.layers, canvas: size,
                              selectedID: selectedSwatchID, scale: viewScale)
            }
        }
        .shadow(color: .black.opacity(0.4), radius: 12, y: 4)
    }

    // MARK: pick

    /// One finger in Color: the loupe follows it, and lifting adds a swatch
    /// from the selected layer. `screen` is in the workspace's coordinates.
    private func pick(at screen: CGPoint, finished: Bool?, canvas: CGSize, rect: CGRect) {
        // From the screen to canvas points, through the view's pan and zoom.
        let point = CGPoint(x: (screen.x - rect.midX - viewOffset.width) / viewScale + canvas.width / 2,
                            y: (screen.y - rect.midY - viewOffset.height) / viewScale + canvas.height / 2)
        guard let layer = session.selected,
              let found = PickProbe.at(point, layer: layer, canvas: canvas, sample: sampleSize,
                                       shown: shownStudy?.view == .simplify ? shownStudy?.pixels : nil)  // the flat color you see
        else {
            probe = nil
            return
        }
        switch finished {
        case nil:
            probe = (found, screen)
        case true?:
            probe = nil
            if let rgb = found.rgb {
                let swatch = Swatch(layerID: layer.id, u: found.u, v: found.v, red: rgb.0, green: rgb.1, blue: rgb.2,
                                    radius: sampleSize.rawValue)
                session.swatches.append(swatch)  // one undo step
                selectedSwatchID = nil  // its panel opens when you choose its chip, not now
            }
        case false?:
            probe = nil  // a second finger: panning or zooming instead
        }
    }

    /// The layers, or while comparing, the layers Compare shows: in Split, A
    /// left of the line over B on the right.
    @ViewBuilder
    private func canvasContent(size: CGSize) -> some View {
        let grid = session.grid.isOn ? session.grid : nil
        let lineWidth = 1.5 / viewScale  // the same thickness on screen at any zoom
        if let compare {
            CompareCanvas(state: compare, clock: blinkClock, layers: session.layers, size: size,
                          grid: grid, gridLineWidth: lineWidth, background: session.background.color)
        } else {
            CanvasContent(layers: session.layers, size: size, grid: grid, gridLineWidth: lineWidth,
                          faintFullImageOf: cropping?.id,
                          replacements: shownStudy.map { [$0.layerID: $0.image] } ?? [:],
                          background: session.background.color)
        }
    }

    // MARK: simplify and highlight

    /// The result to show: for the selected layer, in the view it was made for.
    /// While a new one is made, the last one stays up.
    private var shownStudy: StudyResult? {
        guard colorView != .normal, let study,
              study.layerID == session.selectedID, study.view == colorView else { return nil }
        return study
    }

    /// The swatches Highlight shows, each with its number's highlight color.
    private var highlightSwatches: [(rgb: (Int, Int, Int), index: Int)] {
        session.swatches.enumerated()
            .filter { !highlightSettings.selectedOnly || $0.element.id == selectedSwatchID }
            .map { (($0.element.red, $0.element.green, $0.element.blue), $0.offset) }
    }

    /// Everything Simplify or Highlight depends on; nil when neither is on.
    private var studyKey: String? {
        guard colorView != .normal, let layer = session.selected else { return nil }
        let image = ObjectIdentifier(layer.shownImage).hashValue  // a new image after Look or Edit corners
        switch colorView {
        case .simplify:
            let s = simplifySettings
            return "simplify \(layer.id) \(image) \(s.mode) \(s.count) \(s.smoothing)"
        case .highlight:
            let colors = highlightSwatches.map { "\($0.rgb.0),\($0.rgb.1),\($0.rgb.2)@\($0.index)" }.joined(separator: " ")
            return "highlight \(layer.id) \(image) \(highlightSettings.tolerance) \(colors)"
        case .normal:
            return nil
        }
    }

    /// Transform on: one or two fingers move the selected image, pinch scales,
    /// twist rotates. Transform off: the same gestures pan and zoom the view.
    /// Double-tap fits the view. Each change is applied as a step from the
    /// last one, so a cancelled gesture leaves nothing behind.
    private func canvasGestures(canvas: CGSize, at rect: CGRect) -> CanvasGestureHandlers {
        CanvasGestureHandlers(
            pan: { d in
                if let layer = transformTarget {
                    layer.move(by: CGPoint(x: d.width / (canvas.width * viewScale), y: d.height / (canvas.height * viewScale)))
                } else {
                    viewOffset = CGSize(width: viewOffset.width + d.width, height: viewOffset.height + d.height)
                }
            },
            pinch: { s in
                if let layer = transformTarget {
                    layer.scale(by: s, in: canvas)  // evenly, about its center, in every mode
                } else {
                    viewScale = min(max(viewScale * s, 0.5), 8)
                }
            },
            rotate: { r in transformTarget?.rotate(by: r, in: canvas) },
            doubleTap: { withAnimation { viewScale = 1; viewOffset = .zero } },
            undo: { if canUndo { history.undo() } },
            redo: { if canRedo { history.redo() } },
            began: { history.hold("gesture") },
            ended: {
                history.release("gesture")
                if let layer = transformTarget {
                    gestureLog.notice("Transform ended: \(layer.placementDescription)")
                } else {
                    gestureLog.notice("View ended: scale \(viewScale), offset \(viewOffset.width), \(viewOffset.height)")
                }
            },
            pick: { screen, finished in pick(at: screen, finished: finished, canvas: canvas, rect: rect) })
    }

    /// The layer the gestures move, or nil when they move the view.
    private var transformTarget: Layer? { transformOn ? session.selected : nil }

    // MARK: chrome

    private var chrome: some View {
        VStack(spacing: 0) {
            topBar
            HStack(alignment: .top, spacing: 0) {
                Spacer()
                if colorBarShown, colorPanelOpen, !Theme.isPhone,
                   let index = session.swatches.firstIndex(where: { $0.id == selectedSwatchID }) {
                    let swatch = session.swatches[index]
                    ColorPanel(swatch: swatch, number: index + 1, pointerY: layerRowCenter(swatch.layerID)) {
                        colorPanelOpen = false
                    }
                    .padding(.vertical, 16)  // from under the top bar to just above the bottom bar
                }
                if !Theme.isPhone { layerBar.padding(12) }  // on the phone, Layers opens a sheet
            }
            .frame(maxHeight: .infinity, alignment: .top)  // the swatch panel can run down to the bottom bar
            if colorToolOn, let layer = session.selected, layer.blend != .normal || layer.opacity < 0.995 {
                // Pick, Simplify and Highlight read the layer's own image, not the mix on the canvas.
                Text("Colors are read from this layer at full strength. Flatten to read what you see.")
                    .font(.footnote)
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(Capsule().fill(Theme.bar))
                    .padding(.bottom, 8)
            }
            Group {
                if let cropping, let layer = session.selected, layer.id == cropping.id {
                    CropBar(layer: layer, shape: $cropShape,
                            onCancel: { finishCrop(keep: false) }, onDone: { finishCrop(keep: true) })
                } else if compare != nil {
                    CompareBar(state: Binding(get: { compare ?? CompareState(session: session) }, set: { compare = $0 }),
                               layers: session.layers, clock: blinkClock) { compare = nil }
                } else if gridBarShown {
                    GridBar(session: session) { gridBarShown = false }
                } else if transformOn, let layer = session.selected {
                    TransformBar(layer: layer, mode: $transformMode, canvasSize: session.canvasSize,
                                 onCancel: cancelTransform, onDone: { transformOn = false })
                } else if colorBarShown {
                    ColorBar(session: session, selectedID: $selectedSwatchID, picking: $swatchesOn, view: $colorView,
                             sample: $sampleSize, simplify: $simplifySettings, highlight: $highlightSettings,
                             markersShown: $studyMarkersShown, working: studyWorking) { endTools() }
                } else if let layer = session.selected {
                    LookBar(layer: layer, canvasAspect: session.canvasAspect, onEditCorners: { editCorners(layer) })
                }
            }
            .padding(.horizontal, Theme.isPhone ? 8 : 12)  // full-width bars keep a margin
            .padding(.bottom, Theme.isPhone ? 6 : 12)
            if Theme.isPhone {
                tools
                    .padding(.bottom, 2)
                    .frame(maxWidth: .infinity)
                    .background(Theme.background.ignoresSafeArea(edges: .bottom))
            }
        }
    }

    // MARK: share

    /// Renders the canvas at full resolution, then opens the share sheet.
    private func share(withGrid: Bool) {
        finishCrop(keep: true)
        exporting = true
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(50))  // let "Preparing image…" show before the render
            let url = CanvasExport.render(session, withGrid: withGrid)
            exporting = false
            if let url { shareFile = ShareFile(url: url) } else { shareFailed = true }
        }
    }

    /// The swatches and their best mixes as a PDF, then the share sheet.
    private func shareSwatchSheet() {
        exporting = true
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(50))
            let url = SwatchSheet.render(session)
            exporting = false
            if let url { shareFile = ShareFile(url: url) } else { shareFailed = true }
        }
    }

    /// Home on the left; the tools in the middle; undo and redo, the paint
    /// library, share and full screen on the right.
    private var topBar: some View {
        ZStack {
            if !Theme.isPhone { tools }  // on the phone they're in a row at the bottom
            HStack(spacing: 0) {
                Button {
                    endTools()
                    onGallery()
                } label: {
                    Image(systemName: "house.fill").font(.system(size: 20)).frame(width: 44, height: 44)
                }
                .foregroundStyle(.white)
                .accessibilityLabel("Gallery")
                Spacer()
                Button { history.undo() } label: { Image(systemName: "arrow.uturn.backward").frame(width: 28, height: 44) }
                    .accessibilityLabel("Undo")
                    .keyboardShortcut("z", modifiers: .command)
                    .disabled(!canUndo)
                    .padding(.trailing, 16)
                Button { history.redo() } label: { Image(systemName: "arrow.uturn.forward").frame(width: 28, height: 44) }
                    .accessibilityLabel("Redo")
                    .keyboardShortcut("z", modifiers: [.command, .shift])
                    .disabled(!canRedo)
                    .padding(.trailing, 32)
                HStack(spacing: 16) {
                    if !Theme.isPhone {  // not on the phone yet
                        Button { paintLibraryOpen = true } label: { topIcon("books.vertical") }
                            .accessibilityLabel("Paint library")
                    }
                    Menu {
                        Button("Share image", systemImage: "photo") { share(withGrid: false) }
                        if session.grid.isOn {
                            Button("Share image with grid", systemImage: "square.grid.3x3") { share(withGrid: true) }
                        }
                        if !Theme.isPhone {
                            Button("Share swatch sheet (PDF)", systemImage: "doc.richtext") { shareSwatchSheet() }
                                .disabled(session.swatches.isEmpty)
                        }
                    } label: {
                        topIcon("square.and.arrow.up")
                    }
                    .accessibilityLabel("Share")
                    .disabled(exporting)
                    Button {
                        finishCrop(keep: true)  // the crop bar is hidden in full screen
                        withAnimation { fullScreen = true }
                    } label: {
                        topIcon("arrow.up.left.and.arrow.down.right")
                    }
                    .accessibilityLabel("Full screen")
                }
            }
            .font(.system(size: 20))
        }
        .padding(.horizontal, 12)
        .frame(height: 56)
        .background(Theme.background)
    }

    private func topIcon(_ symbol: String) -> some View {
        Image(systemName: symbol).font(.system(size: 20)).frame(width: 44, height: 44)
    }

    /// The tools, in the middle of the top bar (on the phone, in a row at the
    /// bottom, with Layers). Each one that has a bar at the bottom turns the
    /// others off; tapping it again turns it off.
    private var tools: some View {
        HStack(spacing: Theme.isPhone ? 20 : 16) {
            if Theme.isPhone {  // two buttons, each opening a pop-up with two choices
                addButton
                shapeButton
            } else {
                toolButton("camera", "Camera") { capture = Capture(picked: nil) }
                toolButton("photo.on.rectangle", "Photos") { showPhotos = true }
                toolButton("arrow.up.and.down.and.arrow.left.and.right", "Transform", on: transformOn, action: toggleTransform)
                    .disabled(session.selected == nil)
                toolButton("crop", "Crop", on: cropping != nil, action: toggleCrop)
                    .disabled(session.selected == nil)
            }
            toolButton("square.grid.3x3", "Grid", on: gridBarShown) {
                let on = gridBarShown
                endTools()
                gridBarShown = !on
            }
            toolButton("rectangle.split.2x1", "Compare", on: compare != nil) {
                let on = compare != nil
                endTools()
                if !on {
                    blinkClock.restart()  // starts on A
                    compare = CompareState(session: session)
                }
            }
            .disabled(session.layers.isEmpty)
            if Theme.isPhone {
                toolButton("square.2.layers.3d", "Layers", on: layersSheet) {
                    toolPopup = nil
                    layersSheet = true
                }
            } else {
                toolButton("eyedropper", "Swatches, Simplify and Highlight", on: colorBarShown) {
                    let on = colorBarShown
                    endTools()
                    colorBarShown = !on
                }
                .disabled(session.layers.isEmpty)
            }
        }
    }

    private func toggleTransform() {
        let on = transformOn
        endTools()
        transformOn = !on
    }

    private func toggleCrop() {
        let on = cropping != nil
        endTools()
        if !on, let layer = session.selected { startCrop(layer) }
    }

    // MARK: the phone's combined buttons

    /// Which of the phone's combined buttons has its pop-up open.
    enum ToolPopup { case add, shape }

    /// + : Camera or Photos.
    private var addButton: some View {
        toolButton("plus", "Add an image", on: toolPopup == .add) {
            withAnimation(.snappy) { toolPopup = toolPopup == .add ? nil : .add }
        }
        .overlay(alignment: .bottom) {
            if toolPopup == .add {
                popupChoices([
                    ("camera", "Camera", false, true, { capture = Capture(picked: nil) }),
                    ("photo.on.rectangle", "Photos", false, true, { showPhotos = true }),
                ])
            }
        }
    }

    /// Transform or Crop. Shows the one that's on; choosing it again turns it off.
    private var shapeButton: some View {
        let transformSymbol = "arrow.up.and.down.and.arrow.left.and.right"
        return toolButton(cropping != nil ? "crop" : transformSymbol, "Transform or crop",
                          on: transformOn || cropping != nil || toolPopup == .shape) {
            withAnimation(.snappy) { toolPopup = toolPopup == .shape ? nil : .shape }
        }
        .disabled(session.selected == nil)
        .overlay(alignment: .bottom) {
            if toolPopup == .shape {
                popupChoices([
                    (transformSymbol, "Transform", transformOn, session.selected != nil, toggleTransform),
                    ("crop", "Crop", cropping != nil, session.selected != nil, toggleCrop),
                ])
            }
        }
    }

    /// The pop-up above a combined button: icons with their names. Choosing
    /// one closes it.
    private func popupChoices(_ choices: [(symbol: String, title: String, on: Bool, enabled: Bool, action: () -> Void)]) -> some View {
        Callout {
            HStack(spacing: 18) {
                ForEach(choices, id: \.title) { choice in
                    Button {
                        toolPopup = nil
                        choice.action()
                    } label: {
                        VStack(spacing: 4) {
                            toolIcon(choice.symbol, on: choice.on)
                            Text(choice.title).font(.caption)
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(!choice.enabled)
                }
            }
        }
        .fixedSize()  // its own size, not the button's
        .offset(y: -(44 + 6))  // just above the button
        .transition(.opacity)
    }

    private func toolButton(_ symbol: String, _ label: String, on: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) { toolIcon(symbol, on: on) }.accessibilityLabel(label)
    }

    private func toolIcon(_ symbol: String, on: Bool) -> some View {
        Image(systemName: symbol)
            .font(.system(size: 22))
            .frame(width: 44, height: 44)
            .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                .fill(on ? Theme.accent : Color.clear))
            .foregroundStyle(on ? Theme.onAccent : Color.white)
    }

    /// Thumbnails, top layer first. Expanded (‹), each row also shows its
    /// number, an eye, and blend · opacity. Long-press a layer for moving,
    /// duplicating, hiding and deleting.
    private var layerBar: some View {
        VStack(alignment: .trailing, spacing: 6) {
            if !Theme.isPhone {  // the phone's sheet is always expanded
                Button {
                    withAnimation(.snappy) { layerBarExpanded.toggle() }
                } label: {
                    Image(systemName: layerBarExpanded ? "chevron.right" : "chevron.left")
                        .font(.system(size: 14, weight: .semibold))
                        .frame(width: 48, height: 28)
                }
                .accessibilityLabel(layerBarExpanded ? "Collapse layers" : "Expand layers")
            }
            ForEach(session.layers.reversed()) { layer in  // top layer first
                layerRow(layer)
            }
            if session.layers.isEmpty {
                Text("No layers").font(.caption).foregroundStyle(.secondary).frame(width: 60)
            } else {
                Divider().frame(width: 48)
                layerBarButton("Flatten", systemImage: "square.3.layers.3d.down.right") { flatten() }
                    .disabled(!session.layers.contains(where: \.isVisible))
            }
        }
        .padding(6)
        .themedBar()
    }

    /// An icon in the collapsed bar; icon and title expanded.
    private func layerBarButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            if layerBarExpanded {
                Label(title, systemImage: systemImage).frame(width: 196, height: 36, alignment: .trailing)
            } else {
                Image(systemName: systemImage).frame(width: 48, height: 36)
            }
        }
        .accessibilityLabel(title)
    }

    // MARK: flatten

    /// The visible layers into one new layer on top (see `flattenVisible`).
    private func flatten() {
        finishCrop(keep: true)
        transformOn = false
        compare = nil
        session.flattenVisible()
    }

    /// Where a layer's thumbnail is, down from the top of the layer bar, so
    /// the swatch panel can point at it. Matches the bar's layout: 6 pt of
    /// padding, the 28 pt chevron, then 48 pt rows 6 pt apart, top layer first.
    private func layerRowCenter(_ layerID: UUID) -> CGFloat? {
        guard let index = session.layers.firstIndex(where: { $0.id == layerID }) else { return nil }
        let row = CGFloat(session.layers.count - 1 - index)  // 0 = the top layer, shown first
        let top: CGFloat = 6 + 28 + 6
        return top + row * 54 + 24
    }

    private func layerRow(_ layer: Layer) -> some View {
        let number = (session.layers.firstIndex { $0.id == layer.id } ?? 0) + 1  // 1 = bottom
        let selected = session.selectedID == layer.id
        return HStack(spacing: 10) {
            if layerBarExpanded {
                Button {
                    layer.isVisible.toggle()
                } label: {
                    Image(systemName: layer.isVisible ? "eye" : "eye.slash")
                        .frame(width: 32, height: 44)
                        .foregroundStyle(layer.isVisible ? .primary : .secondary)
                }
                .accessibilityLabel(layer.isVisible ? "Hide layer \(number)" : "Show layer \(number)")
                Button {
                    session.selectedID = layer.id
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(layer.name.hasPrefix("Flattened") ? layer.name : "Layer \(number)")  // "Flattened 1"
                            .font(.subheadline.weight(selected ? .semibold : .regular))
                            .lineLimit(1)
                        Text("\(layer.blend.rawValue) · \(Int((layer.opacity * 100).rounded()))%")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    .frame(width: 96, alignment: .leading)
                }
            }
            Button {
                session.selectedID = layer.id
            } label: {
                Image(uiImage: layer.shownImage)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 48, height: 48)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .opacity(layer.isVisible ? 1 : 0.35)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.accent, lineWidth: selected ? 3 : 0))
                    .overlay(alignment: .bottomLeading) { compareBadge(layer) }
                    .overlay(alignment: .leading) {
                        if session.swatches.contains(where: { $0.layerID == layer.id }) {  // this layer has swatches
                            SwatchBadge().offset(x: -8)  // half over the thumbnail's left edge
                        }
                    }
            }
            .accessibilityLabel("Layer \(number)")
        }
        .contentShape(Rectangle())
        .contextMenu {
            Button("Move up", systemImage: "arrow.up") { session.move(layer, by: 1) }
                .disabled(number == session.layers.count)
            Button("Move down", systemImage: "arrow.down") { session.move(layer, by: -1) }
                .disabled(number == 1)
            Button("Bring to front", systemImage: "square.3.layers.3d.top.filled") { session.move(layer, to: session.layers.count - 1) }
                .disabled(number == session.layers.count)
            Button("Send to back", systemImage: "square.3.layers.3d.bottom.filled") { session.move(layer, to: 0) }
                .disabled(number == 1)
            Divider()
            Button("Edit corners…", systemImage: "perspective") { editCorners(layer) }
                .disabled(layer.source == nil)
            Button("Duplicate", systemImage: "plus.square.on.square") { session.duplicate(layer) }
            Button(layer.isVisible ? "Hide" : "Show", systemImage: layer.isVisible ? "eye.slash" : "eye") {
                layer.isVisible.toggle()
            }
            Button("Delete", systemImage: "trash", role: .destructive) { session.delete(layer) }
        }
    }

    /// While comparing: the layer's number (as in the A and B menus), and A or B.
    @ViewBuilder
    private func compareBadge(_ layer: Layer) -> some View {
        if let compare, let index = session.layers.firstIndex(where: { $0.id == layer.id }) {
            let role = layer.id == compare.a ? "A" : (compare.mode.needsB && layer.id == compare.b ? "B" : nil)
            Text(role.map { "\(index + 1) \($0)" } ?? "\(index + 1)")
                .font(.caption2.weight(.bold))
                .padding(.horizontal, 4)
                .background(RoundedRectangle(cornerRadius: 4).fill(role == nil ? Color.black.opacity(0.6) : Theme.accent))
                .foregroundStyle(.white)
                .padding(2)
        }
    }

    private var exitFullScreenButton: some View {
        // Where Full screen is in the top bar: top right, 12 pt in, the top bar's height.
        VStack {
            HStack {
                Spacer()
                Button {
                    withAnimation { fullScreen = false }
                } label: {
                    Image(systemName: "arrow.down.right.and.arrow.up.left")
                        .font(.system(size: 20))
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(Color.white.opacity(0.12)))
                }
                .opacity(0.6)
                .accessibilityLabel("Exit full screen")
            }
            .frame(height: 56)
            Spacer()
        }
        .padding(.horizontal, 12)
    }
}

/// The selected layer's Look, cut down: opacity first and largest, blend,
/// Adjust (levels, hue / saturation, colorize, invert), and ⋯ for Fit, Flip
/// and Edit corners. Transform and Crop are in the left tool strip.
struct LookBar: View {
    @Bindable var layer: Layer
    let canvasAspect: CGFloat
    var onEditCorners: () -> Void

    @Environment(History.self) private var history
    @State private var adjusting = false

    var body: some View {
        Group {
            if Theme.isPhone {  // three rows: name and buttons, opacity, blend
                VStack(spacing: 10) {
                    HStack(spacing: 0) {
                        title
                        Spacer(minLength: 8)
                        buttons
                    }
                    opacity
                    blend
                }
            } else {
                HStack(spacing: BarSpacing.group) {
                    title.frame(maxWidth: 180, alignment: .leading)
                    opacity
                    blend.frame(width: 250)
                    buttons
                    Spacer(minLength: 0)
                }
            }
        }
        .bottomBar()
    }

    private var title: some View {
        HStack(spacing: 12) {
            Image(systemName: "square.2.layers.3d").font(.system(size: 20))
            Text(layer.name).font(.headline).lineLimit(1)
        }
    }

    private var opacity: some View {
        HStack(spacing: BarSpacing.icon) {
            Text("Opacity")
            Slider(value: $layer.opacity, in: 0...1) { editing in
                if editing { history.hold("opacity") } else { history.release("opacity") }  // one drag, one step
            }
            .frame(width: Theme.isPhone ? nil : 200)  // on the phone, the row's width
            Text("\(Int((layer.opacity * 100).rounded()))%")
                .monospacedDigit()
                .lineLimit(1)
                .fixedSize()  // "100%" stays on one line
                .frame(minWidth: 48, alignment: .trailing)
        }
    }

    private var blend: some View {
        Picker("Blend", selection: $layer.blend) {
            ForEach(Blend.allCases) { Text($0.rawValue).tag($0) }
        }
        .pickerStyle(.segmented)
    }

    private var buttons: some View {
        HStack(spacing: Theme.isPhone ? 4 : BarSpacing.icon) {
            Button {
                adjusting = true
            } label: {
                icon("slider.horizontal.3")
                    .overlay(alignment: .topTrailing) {
                        if !layer.adjustments.isIdentity {  // this layer has adjustments
                            Circle().fill(Theme.accent).frame(width: 8, height: 8).offset(x: -6, y: 8)
                        }
                    }
            }
            .accessibilityLabel("Adjust")
            .popover(isPresented: $adjusting) { LookPanel(layer: layer) }
            Button { layer.flipHorizontal() } label: { icon("arrow.left.and.right") }
                .accessibilityLabel("Flip horizontal")
            Button { layer.flipVertical() } label: { icon("arrow.up.and.down") }
                .accessibilityLabel("Flip vertical")
            Menu {
                Button("Fit", systemImage: "arrow.up.left.and.down.right.magnifyingglass") { layer.fit(canvasAspect: canvasAspect) }
                Divider()
                Button("Edit corners…", systemImage: "perspective", action: onEditCorners)
                    .disabled(layer.source == nil)  // added before photos were kept
            } label: {
                icon("ellipsis.circle")
            }
            .accessibilityLabel("More")
        }
    }

    private func icon(_ symbol: String) -> some View {
        Image(systemName: symbol).font(.system(size: 20)).frame(width: 44, height: 44)
    }
}

/// A layer shown simplified or highlighted: the image, and for Simplify the
/// colors it found, and its pixels so Pick reads what you see.
struct StudyResult {
    let layerID: UUID
    let view: ColorView
    let image: UIImage
    let simplified: ColorStudy.Simplified?
    let pixels: PixelBuffer?
}

/// A layer whose corners are being edited, and the rectangle found in its photo.
struct CornerEdit: Identifiable {
    let layer: Layer
    let detected: Corners?
    var id: UUID { layer.id }
}

/// The small circle on a layer thumbnail's left edge: it has swatches.
struct SwatchBadge: View {
    var body: some View {
        Image(systemName: "eyedropper")
            .font(.system(size: 7, weight: .bold))
            .foregroundStyle(.white)
            .frame(width: 16, height: 16)
            .background(Circle().fill(Theme.purple))
            .shadow(color: .black.opacity(0.3), radius: 1)
            .accessibilityLabel("Has swatches")
    }
}

/// One rendered image on its way to the share sheet.
struct ShareFile: Identifiable {
    let id = UUID()
    let url: URL
}

/// The Grid tool's options: on / off, rows and columns, square cells, color and opacity.
struct GridBar: View {
    @Bindable var session: TransferSession
    var onDone: () -> Void

    var body: some View {
        Group {
            if Theme.isPhone {  // three rows: title and Done, counts, colors and opacity
                VStack(spacing: 8) {
                    HStack {
                        title
                        Spacer(minLength: 8)
                        DoneButton(action: onDone)
                    }
                    HStack(spacing: 20) {
                        count("Rows", $session.grid.rows)
                        count("Columns", $session.grid.columns)
                        Spacer(minLength: 0)
                        squareCells
                    }
                    HStack(spacing: 12) {
                        colors
                        Slider(value: $session.grid.opacity, in: 0.1...1)
                            .accessibilityLabel("Opacity")
                    }
                }
            } else {
                HStack(spacing: BarSpacing.group) {
                    title
                    count("Rows", $session.grid.rows)
                    count("Columns", $session.grid.columns)
                    squareCells
                    colors
                    HStack(spacing: 16) {
                        Text("Opacity")
                        Slider(value: $session.grid.opacity, in: 0.1...1).frame(width: 140)
                    }
                    Spacer(minLength: 0)
                    DoneButton(action: onDone)
                }
            }
        }
        .bottomBar()
    }

    private var title: some View {
        HStack(spacing: 24) {
            BarTitle("Grid", symbol: "square.grid.3x3")
            Toggle("Grid", isOn: $session.grid.isOn)
                .labelsHidden()
                .fixedSize()
        }
    }

    private var squareCells: some View {
        Button {
            session.grid.squareCells(canvasAspect: session.canvasAspect)
        } label: {
            Image(systemName: "square.grid.3x3.square").font(.system(size: 24)).frame(width: 44, height: 44)
        }
        .accessibilityLabel("Square cells")
    }

    private var colors: some View {
        HStack(spacing: 3) {
            ForEach(GridColor.allCases) { color in
                Button {
                    session.grid.color = color
                } label: {
                    Circle()
                        .fill(color.color)
                        .frame(width: 26, height: 26)
                        .overlay(Circle().stroke(Color.white.opacity(0.5), lineWidth: 1))
                        .padding(3)
                        .overlay(Circle().stroke(Theme.accent, lineWidth: session.grid.color == color ? 3 : 0))
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel(color.rawValue.capitalized)
                .accessibilityAddTraits(session.grid.color == color ? .isSelected : [])
            }
        }
    }

    /// "Rows  4 ⌄": a menu of 1 to 10.
    private func count(_ title: String, _ value: Binding<Int>) -> some View {
        HStack(spacing: 10) {
            Text(title).foregroundStyle(.secondary)
            Picker(title, selection: value) {
                ForEach(GridSettings.range, id: \.self) { Text("\($0)").tag($0) }
            }
            .pickerStyle(.menu)
            .labelsHidden()
        }
        .fixedSize()
    }
}
