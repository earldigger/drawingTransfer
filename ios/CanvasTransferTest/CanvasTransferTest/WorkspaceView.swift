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
            }
        }
        .environment(\.colorScheme, .dark)
        .statusBarHidden(fullScreen)
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
        ZStack {
            Rectangle().fill(Color.white)
            ForEach(session.layers) { layer in
                if layer.isVisible { layerView(layer, canvas: size) }
            }
        }
        .frame(width: size.width, height: size.height)
        .clipped()  // first, so the group below is only ever canvas-sized
        .compositingGroup()  // so Multiply blends with the layers below, not the background
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

    /// The layer's image, clipped to its crop. While it is being cropped, the
    /// whole image also shows faintly underneath, so you see what's cut off.
    @ViewBuilder
    private func layerView(_ layer: Layer, canvas: CGSize) -> some View {
        let w = layer.width * canvas.width, h = w / layer.aspect, c = layer.crop
        let image = Image(uiImage: layer.image).resizable().frame(width: w, height: h)
        if cropping?.id == layer.id {
            placed(image, layer, canvas: canvas, opacity: layer.opacity * 0.3)
        }
        // Clipped, not masked: a mask is drawn offscreen at the image's full
        // size, and past the iPad's texture limit a large image vanished.
        let cropped = image
            .offset(x: -c.minX * w, y: -c.minY * h)
            .frame(width: c.width * w, height: c.height * h, alignment: .topLeading)
            .clipped()
            .offset(x: c.minX * w, y: c.minY * h)
            .frame(width: w, height: h, alignment: .topLeading)
        placed(cropped, layer, canvas: canvas, opacity: layer.opacity)
    }

    private func placed(_ content: some View, _ layer: Layer, canvas: CGSize, opacity: Double) -> some View {
        content
            .rotationEffect(layer.rotation)
            .position(x: layer.center.x * canvas.width, y: layer.center.y * canvas.height)
            .opacity(opacity)
            .blendMode(layer.blend.mode)
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
            if let layer = session.selected {
                if cropping?.id == layer.id {
                    CropBar(layer: layer, shape: $cropShape,
                            onCancel: { finishCrop(keep: false) }, onDone: { finishCrop(keep: true) })
                        .padding(.bottom, 12)
                } else {
                    LookBar(layer: layer, transformOn: $transformOn, canvasAspect: session.canvasAspect,
                            onCrop: { startCrop(layer) })
                        .padding(.bottom, 12)
                }
            }
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
