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
    @State private var fullScreen = false
    @State private var viewScale: CGFloat = 1
    @State private var viewOffset: CGSize = .zero
    // While cropping: which layer, its crop before (for Cancel), and whether
    // Transform was on (it comes back after Done).
    @State private var cropping: (id: UUID, before: CGRect, wasTransforming: Bool)? = nil
    @State private var cropShape: CropShape = .free
    @State private var gridBarShown = false
    @State private var exporting = false  // rendering the image to share
    @State private var shareFile: ShareFile? = nil
    @State private var shareFailed = false

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
                CanvasGestureView(handlers: canvasGestures(canvas: rect.size))
                canvas(size: rect.size)
                    .scaleEffect(viewScale)
                    .offset(viewOffset)
                    .position(x: rect.midX, y: rect.midY)
                if fullScreen {
                    exitFullScreenButton
                } else {
                    chrome
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
        }
    }

    // MARK: crop

    private func startCrop(_ layer: Layer) {
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

    /// Off while cropping, which has its own Cancel.
    private var canUndo: Bool { cropping == nil && history.canUndo }
    private var canRedo: Bool { cropping == nil && history.canRedo }

    // MARK: canvas

    private func canvas(size: CGSize) -> some View {
        CanvasContent(layers: session.layers, size: size, grid: session.grid.isOn ? session.grid : nil,
                      gridLineWidth: 1.5 / viewScale,  // the same thickness on screen at any zoom
                      faintFullImageOf: cropping?.id)
        .allowsHitTesting(false)  // touches go to the gesture view underneath
        .overlay {
            if let cropping, let layer = session.selected, layer.id == cropping.id {
                CropFrame(layer: layer, canvas: size, shape: cropShape)
            } else if transformOn, let layer = session.selected {
                // Outlines what shows: the crop, turned and placed with the layer.
                let w = layer.width * size.width, h = w / layer.aspect, c = layer.crop
                Rectangle()
                    .stroke(Color.blue, lineWidth: 2)
                    .frame(width: c.width * w, height: c.height * h)
                    .position(x: c.midX * w, y: c.midY * h)
                    .frame(width: w, height: h)
                    .rotationEffect(layer.rotation)
                    .position(x: layer.center.x * size.width, y: layer.center.y * size.height)
                    .allowsHitTesting(false)
            }
        }
        .shadow(color: .black.opacity(0.4), radius: 12, y: 4)
    }

    /// Transform on: one or two fingers move the selected image, pinch scales,
    /// twist rotates. Transform off: the same gestures pan and zoom the view.
    /// Double-tap fits the view. Each change is applied as a step from the
    /// last one, so a cancelled gesture leaves nothing behind.
    private func canvasGestures(canvas: CGSize) -> CanvasGestureHandlers {
        CanvasGestureHandlers(
            pan: { d in
                if let layer = transformTarget {
                    // The center stays within half a canvas of the edges, so the image can't be lost.
                    layer.center = CGPoint(x: min(max(layer.center.x + d.width / (canvas.width * viewScale), -0.5), 1.5),
                                           y: min(max(layer.center.y + d.height / (canvas.height * viewScale), -0.5), 1.5))
                } else {
                    viewOffset = CGSize(width: viewOffset.width + d.width, height: viewOffset.height + d.height)
                }
            },
            pinch: { s in
                if let layer = transformTarget {
                    layer.width = min(max(layer.width * s, 0.03), Layer.maxWidth)
                } else {
                    viewScale = min(max(viewScale * s, 0.5), 8)
                }
            },
            rotate: { r in transformTarget?.rotation += r },
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
            })
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
                layerBar.padding(12)
            }
            Spacer()
            Group {
                if let cropping, let layer = session.selected, layer.id == cropping.id {
                    CropBar(layer: layer, shape: $cropShape,
                            onCancel: { finishCrop(keep: false) }, onDone: { finishCrop(keep: true) })
                } else if gridBarShown {
                    GridBar(session: session) { gridBarShown = false }
                } else if let layer = session.selected {
                    LookBar(layer: layer, transformOn: $transformOn, canvasAspect: session.canvasAspect,
                            onCrop: { startCrop(layer) })
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

    private var toolStrip: some View {
        VStack(spacing: 6) {
            toolButton("camera", "Camera") { capture = Capture(picked: nil) }
            toolButton("photo.on.rectangle", "Photos") { showPhotos = true }
            toolButton("arrow.up.and.down.and.arrow.left.and.right", "Transform", on: transformOn) {
                transformOn.toggle()
            }
            .disabled(session.selected == nil || cropping != nil)
            toolButton("square.grid.3x3", "Grid", on: gridBarShown) {
                finishCrop(keep: true)
                if gridBarShown {
                    gridBarShown = false
                } else {
                    gridBarShown = true
                    session.grid.isOn = true  // opening Grid shows it
                }
            }
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

    private var layerBar: some View {
        VStack(spacing: 6) {
            ForEach(session.layers.reversed()) { layer in  // top layer first
                Button {
                    session.selectedID = layer.id
                } label: {
                    Image(uiImage: layer.image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 48, height: 48)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .opacity(layer.isVisible ? 1 : 0.35)
                        .overlay(RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.blue, lineWidth: session.selectedID == layer.id ? 3 : 0))
                }
                .contextMenu {
                    Button(layer.isVisible ? "Hide" : "Show") { layer.isVisible.toggle() }
                    Button("Delete", role: .destructive) { session.delete(layer) }
                }
                .accessibilityLabel(layer.name)
            }
            if session.layers.isEmpty {
                Text("No layers").font(.caption).foregroundStyle(.secondary).frame(width: 60)
            }
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
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
/// Transform, Fit and Crop.
struct LookBar: View {
    @Bindable var layer: Layer
    @Binding var transformOn: Bool
    let canvasAspect: CGFloat
    var onCrop: () -> Void

    @Environment(History.self) private var history

    var body: some View {
        HStack(spacing: 16) {
            Text(layer.name).font(.subheadline.weight(.semibold)).lineLimit(1).frame(maxWidth: 140, alignment: .leading)
            Text("Opacity")
            Slider(value: $layer.opacity, in: 0...1) { editing in
                if editing { history.hold("opacity") } else { history.release("opacity") }  // one drag, one step
            }
            .frame(width: 240)
            Text("\(Int((layer.opacity * 100).rounded()))%").monospacedDigit().frame(width: 44, alignment: .trailing)
            Picker("Blend", selection: $layer.blend) {
                ForEach(Blend.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)
            Toggle("Transform", isOn: $transformOn).toggleStyle(.button)
            Button("Fit") { layer.fit(canvasAspect: canvasAspect) }
            Button("Crop", systemImage: "crop", action: onCrop)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }
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
