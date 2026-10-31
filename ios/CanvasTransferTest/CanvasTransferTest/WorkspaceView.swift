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
    @State private var workspace = Workspace.transfer
    @State private var pickOn = true  // Color: one finger picks
    @State private var sampleSize = SampleSize.small
    @State private var selectedSwatchID: UUID? = nil
    @State private var probe: (pick: PickProbe, screen: CGPoint)? = nil  // while a finger is picking
    @State private var colorView = ColorView.normal  // Color: Simplify or Highlight the selected layer
    @State private var simplifySettings = SimplifySettings()
    @State private var highlightSettings = HighlightSettings()
    @State private var study: StudyResult? = nil  // the selected layer, simplified or highlighted
    @State private var studyWorking = false
    @State private var colorPanelOpen = true  // Details | Paints & mixes for the selected swatch

    var body: some View {
        GeometryReader { geo in
            let margins = fullScreen ? EdgeInsets() : EdgeInsets(top: 64, leading: 84, bottom: 84, trailing: 96)
            let area = CGSize(width: geo.size.width - margins.leading - margins.trailing,
                              height: geo.size.height - margins.top - margins.bottom)
            let fitted = fitRect(session.canvasSize, in: area, margin: fullScreen ? 0 : 12)
            let rect = fitted.offsetBy(dx: margins.leading, dy: margins.top)
            ZStack {
                (fullScreen ? Color.black : Color(white: 0.23)).ignoresSafeArea()
                // Under the canvas, which lets touches through except on crop handles.
                CanvasGestureView(handlers: canvasGestures(canvas: rect.size, at: rect),
                                  picking: workspace == .color && pickOn && !fullScreen)
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
                        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13)))
                }
            }
        }
        .environment(\.colorScheme, .dark)
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
            if id != nil { colorPanelOpen = true }  // choosing a swatch opens its panel again
        }
        .onChange(of: transformOn) { _, on in
            if on { noteTransformStart() } else { transformStart = nil }
        }
        .onChange(of: workspace) { _, now in
            // Transfer's tools close in Color, and the reverse.
            finishCrop(keep: true)
            transformOn = false
            compare = nil
            gridBarShown = false
            probe = nil
            colorView = .normal
            if now == .color { pickOn = true }
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
            if workspace == .color {
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
                selectedSwatchID = swatch.id
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
                          grid: grid, gridLineWidth: lineWidth)
        } else {
            CanvasContent(layers: session.layers, size: size, grid: grid, gridLineWidth: lineWidth,
                          faintFullImageOf: cropping?.id,
                          replacements: shownStudy.map { [$0.layerID: $0.image] } ?? [:])
        }
    }

    // MARK: simplify and highlight

    /// The result to show: for the selected layer, in the view it was made for.
    /// While a new one is made, the last one stays up.
    private var shownStudy: StudyResult? {
        guard workspace == .color, colorView != .normal, let study,
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
        guard workspace == .color, colorView != .normal, let layer = session.selected else { return nil }
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
                toolStrip.padding(12)
                Spacer()
                if workspace == .color, colorPanelOpen,
                   let index = session.swatches.firstIndex(where: { $0.id == selectedSwatchID }) {
                    ColorPanel(swatch: session.swatches[index], number: index + 1) { colorPanelOpen = false }
                        .padding(.top, 12)
                }
                layerBar.padding(12)
            }
            Spacer()
            if workspace == .color, let layer = session.selected, layer.blend != .normal || layer.opacity < 0.995 {
                // Pick, Simplify and Highlight read the layer's own image, not the mix on the canvas.
                Text("Colors are read from this layer at full strength. Flatten to read what you see.")
                    .font(.footnote)
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(Capsule().fill(Color(white: 0.13).opacity(0.95)))
                    .padding(.bottom, 8)
            }
            Group {
                if workspace == .color {
                    if gridBarShown {
                        GridBar(session: session) { gridBarShown = false }
                    } else if colorView == .simplify {
                        SimplifyBar(settings: $simplifySettings, result: shownStudy?.simplified, working: studyWorking) {
                            colorView = .normal
                        }
                    } else if colorView == .highlight {
                        HighlightBar(settings: $highlightSettings, swatches: session.swatches, selectedID: $selectedSwatchID,
                                     working: studyWorking) { colorView = .normal }
                    } else {
                        SwatchBar(session: session, selectedID: $selectedSwatchID, sample: $sampleSize)
                    }
                } else if let cropping, let layer = session.selected, layer.id == cropping.id {
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
                } else if let layer = session.selected {
                    LookBar(layer: layer, transformOn: $transformOn, canvasAspect: session.canvasAspect,
                            onCrop: { startCrop(layer) }, onEditCorners: { editCorners(layer) })
                }
            }
            .padding(.bottom, 12)
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

    private var topBar: some View {
        HStack {
            Text("Transfer test").font(.headline)
            Spacer()
            Picker("Workspace", selection: $workspace) {
                ForEach(Workspace.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 220)
            Spacer()
            Button { history.undo() } label: { Image(systemName: "arrow.uturn.backward") }
                .accessibilityLabel("Undo")
                .keyboardShortcut("z", modifiers: .command)
                .disabled(!canUndo)
            Button { history.redo() } label: { Image(systemName: "arrow.uturn.forward") }
                .accessibilityLabel("Redo")
                .keyboardShortcut("z", modifiers: [.command, .shift])
                .disabled(!canRedo)
                .padding(.trailing, 12)
            Menu {
                ForEach(TransferSession.canvasSizes.indices, id: \.self) { i in
                    let size = TransferSession.canvasSizes[i]
                    Button("\(Int(size.width)) × \(Int(size.height)) in") { session.canvasSize = size }
                }
                Button("Landscape / portrait") {
                    session.canvasSize = CGSize(width: session.canvasSize.height, height: session.canvasSize.width)
                }
            } label: {
                Label("\(Int(session.canvasSize.width)) × \(Int(session.canvasSize.height)) in", systemImage: "rectangle.portrait")
            }
            Button {
                finishCrop(keep: true)  // the crop bar is hidden in full screen
                withAnimation { fullScreen = true }
            } label: {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
            }
            .accessibilityLabel("Full screen")
            .padding(.leading, 12)
            Menu {
                Button("Share image", systemImage: "photo") { share(withGrid: false) }
                if session.grid.isOn {
                    Button("Share image with grid", systemImage: "square.grid.3x3") { share(withGrid: true) }
                }
            } label: {
                Image(systemName: "square.and.arrow.up")
            }
            .accessibilityLabel("Share")
            .disabled(exporting)
            .padding(.leading, 12)
        }
        .padding(.horizontal, 16)
        .frame(height: 52)
        .background(Color(white: 0.13))
    }

    @ViewBuilder
    private var toolStrip: some View {
        if workspace == .color {
            VStack(spacing: 6) {
                toolButton("eyedropper", "Pick", on: pickOn) { pickOn.toggle() }
                    .disabled(session.layers.isEmpty)
                toolButton("circle.lefthalf.filled", "Simplify", on: colorView == .simplify) {
                    gridBarShown = false
                    colorView = colorView == .simplify ? .normal : .simplify
                }
                .disabled(session.selected == nil)
                toolButton("highlighter", "Highlight", on: colorView == .highlight) {
                    gridBarShown = false
                    colorView = colorView == .highlight ? .normal : .highlight
                }
                .disabled(session.selected == nil)
                gridTool
            }
            .padding(6)
            .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
        } else {
            transferTools
        }
    }

    private var gridTool: some View {
        toolButton("square.grid.3x3", "Grid", on: gridBarShown) {
            finishCrop(keep: true)
            compare = nil
            if gridBarShown {
                gridBarShown = false
            } else {
                gridBarShown = true
                session.grid.isOn = true  // opening Grid shows it
            }
        }
    }

    private var transferTools: some View {
        VStack(spacing: 6) {
            toolButton("camera", "Camera") { capture = Capture(picked: nil) }
            toolButton("photo.on.rectangle", "Photos") { showPhotos = true }
            toolButton("arrow.up.and.down.and.arrow.left.and.right", "Transform", on: transformOn) {
                transformOn.toggle()
            }
            .disabled(session.selected == nil || cropping != nil)
            gridTool
            toolButton("rectangle.split.2x1", "Compare", on: compare != nil) {
                finishCrop(keep: true)
                gridBarShown = false
                blinkClock.restart()  // starts on A
                compare = compare == nil ? CompareState(session: session) : nil
            }
            .disabled(session.layers.isEmpty)
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }

    private func toolButton(_ symbol: String, _ label: String, on: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) { toolIcon(symbol, on: on) }.accessibilityLabel(label)
    }

    private func toolIcon(_ symbol: String, on: Bool) -> some View {
        Image(systemName: symbol)
            .font(.system(size: 20))
            .frame(width: 44, height: 44)
            .background(RoundedRectangle(cornerRadius: 10).fill(on ? Color.blue : Color.clear))
            .foregroundStyle(.white)
    }

    /// Thumbnails, top layer first. Expanded (‹), each row also shows its
    /// number, an eye, and blend · opacity. Long-press a layer for moving,
    /// duplicating, hiding and deleting.
    private var layerBar: some View {
        VStack(alignment: .trailing, spacing: 6) {
            Button {
                withAnimation(.snappy) { layerBarExpanded.toggle() }
            } label: {
                Image(systemName: layerBarExpanded ? "chevron.right" : "chevron.left")
                    .font(.system(size: 14, weight: .semibold))
                    .frame(width: 48, height: 28)
            }
            .accessibilityLabel(layerBarExpanded ? "Collapse layers" : "Expand layers")
            ForEach(session.layers.reversed()) { layer in  // top layer first
                layerRow(layer)
            }
            if session.layers.isEmpty {
                Text("No layers").font(.caption).foregroundStyle(.secondary).frame(width: 60)
            } else {
                Divider().frame(width: 48)
                layerBarButton("Flatten", systemImage: "square.3.layers.3d.down.right") { flatten() }
                    .disabled(!session.layers.contains(where: \.isVisible))
                if let layer = session.selected, layer.isFlattened {
                    layerBarButton("Update", systemImage: "arrow.triangle.2.circlepath") { update(layer) }
                }
            }
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
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

    /// A flattened layer rendered again from what's visible now.
    private func update(_ layer: Layer) {
        finishCrop(keep: true)
        transformOn = false
        compare = nil
        session.update(layer)
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
                        Text(layer.isFlattened ? layer.name : "Layer \(number)")  // "Flattened 1"
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
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.blue, lineWidth: selected ? 3 : 0))
                    .overlay(alignment: .bottomLeading) { compareBadge(layer) }
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
            if layer.isFlattened {
                Button("Update", systemImage: "arrow.triangle.2.circlepath") { update(layer) }
            }
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
                .background(RoundedRectangle(cornerRadius: 4).fill(role == nil ? Color.black.opacity(0.6) : Color.blue))
                .foregroundStyle(.white)
                .padding(2)
        }
    }

    private var exitFullScreenButton: some View {
        VStack {
            HStack {
                Button {
                    withAnimation { fullScreen = false }
                } label: {
                    Image(systemName: "arrow.down.right.and.arrow.up.left")
                        .frame(width: 40, height: 40)
                        .background(Circle().fill(Color.white.opacity(0.12)))
                }
                .opacity(0.6)
                .accessibilityLabel("Exit full screen")
                Spacer()
            }
            Spacer()
        }
        .padding(16)
    }
}

/// The selected layer's Look, cut down: opacity first and largest, blend,
/// Adjust (levels, hue / saturation, colorize, invert), Transform, Crop, and
/// ⋯ for Fit, Flip and Edit corners.
struct LookBar: View {
    @Bindable var layer: Layer
    @Binding var transformOn: Bool
    let canvasAspect: CGFloat
    var onCrop: () -> Void
    var onEditCorners: () -> Void

    @Environment(History.self) private var history
    @State private var adjusting = false

    var body: some View {
        HStack(spacing: 14) {
            Text(layer.name).font(.subheadline.weight(.semibold)).lineLimit(1).frame(maxWidth: 110, alignment: .leading)
            Text("Opacity")
            Slider(value: $layer.opacity, in: 0...1) { editing in
                if editing { history.hold("opacity") } else { history.release("opacity") }  // one drag, one step
            }
            .frame(width: 200)
            Text("\(Int((layer.opacity * 100).rounded()))%").monospacedDigit().frame(width: 44, alignment: .trailing)
            Picker("Blend", selection: $layer.blend) {
                ForEach(Blend.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 250)
            Button {
                adjusting = true
            } label: {
                Label("Adjust", systemImage: "slider.horizontal.3")
                    .overlay(alignment: .topTrailing) {
                        if !layer.adjustments.isIdentity {  // this layer has adjustments
                            Circle().fill(Color.blue).frame(width: 8, height: 8).offset(x: 5, y: -3)
                        }
                    }
            }
            .popover(isPresented: $adjusting) { LookPanel(layer: layer) }
            Toggle("Transform", isOn: $transformOn).toggleStyle(.button)
            Button("Crop", systemImage: "crop", action: onCrop)
            Menu {
                Button("Fit", systemImage: "arrow.up.left.and.down.right.magnifyingglass") { layer.fit(canvasAspect: canvasAspect) }
                Button("Flip horizontal", systemImage: "arrow.left.and.right") { layer.flipHorizontal() }
                Button("Flip vertical", systemImage: "arrow.up.and.down") { layer.flipVertical() }
                Divider()
                Button("Edit corners…", systemImage: "perspective", action: onEditCorners)
                    .disabled(layer.source == nil)  // added before photos were kept
            } label: {
                Image(systemName: "ellipsis.circle").font(.system(size: 20))
            }
            .accessibilityLabel("More")
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
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

/// One rendered image on its way to the share sheet.
struct ShareFile: Identifiable {
    let id = UUID()
    let url: URL
}

/// The Grid tool's options: shown, rows and columns, square cells, color and opacity.
struct GridBar: View {
    @Bindable var session: TransferSession
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: 16) {
            Toggle("Grid", systemImage: "square.grid.3x3", isOn: $session.grid.isOn)
                .toggleStyle(.button)
            Stepper("Rows \(session.grid.rows)", value: $session.grid.rows, in: GridSettings.range)
                .fixedSize()
            Stepper("Columns \(session.grid.columns)", value: $session.grid.columns, in: GridSettings.range)
                .fixedSize()
            Button("Square cells") { session.grid.squareCells(canvasAspect: session.canvasAspect) }
            HStack(spacing: 8) {
                ForEach(GridColor.allCases) { color in
                    Button {
                        session.grid.color = color
                    } label: {
                        Circle()
                            .fill(color.color)
                            .frame(width: 26, height: 26)
                            .overlay(Circle().stroke(Color.white.opacity(0.5), lineWidth: 1))
                            .padding(3)
                            .overlay(Circle().stroke(Color.blue, lineWidth: session.grid.color == color ? 3 : 0))
                            .frame(width: 44, height: 44)
                    }
                    .accessibilityLabel(color.rawValue.capitalized)
                    .accessibilityAddTraits(session.grid.color == color ? .isSelected : [])
                }
            }
            Text("Opacity")
            Slider(value: $session.grid.opacity, in: 0.1...1).frame(width: 140)
            Button("Done", action: onDone).buttonStyle(.borderedProminent)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }
}
