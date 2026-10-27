import PhotosUI
import SwiftUI
import UIKit

/// One photo on its way in, from Camera (`picked == nil`) or Photos.
struct Capture: Identifiable {
    let id = UUID()
    let kind: LayerKind
    let picked: UIImage?
}

/// Transfer workspace, cut down to what this test needs: tools on the left,
/// layers on the right, the selected layer's look at the bottom, and the
/// canvas fitted between them.
struct WorkspaceView: View {
    @Environment(TransferSession.self) private var session

    @State private var capture: Capture? = nil
    @State private var showPhotos = false
    @State private var photoItem: PhotosPickerItem? = nil
    @State private var photosKind: LayerKind = .reference
    @State private var transformOn = false
    @State private var fullScreen = false
    @State private var viewScale: CGFloat = 1
    @State private var viewOffset: CGSize = .zero
    @State private var gestureStart: (center: CGPoint, width: CGFloat, rotation: Angle, scale: CGFloat, offset: CGSize)? = nil

    var body: some View {
        GeometryReader { geo in
            let margins = fullScreen ? EdgeInsets() : EdgeInsets(top: 64, leading: 84, bottom: 84, trailing: 96)
            let area = CGSize(width: geo.size.width - margins.leading - margins.trailing,
                              height: geo.size.height - margins.top - margins.bottom)
            let fitted = fitRect(session.canvasSize, in: area, margin: fullScreen ? 0 : 12)
            let rect = fitted.offsetBy(dx: margins.leading, dy: margins.top)
            ZStack {
                (fullScreen ? Color.black : Color(white: 0.23)).ignoresSafeArea()
                canvas(size: rect.size)
                    .scaleEffect(viewScale)
                    .offset(viewOffset)
                    .position(x: rect.midX, y: rect.midY)
                    .contentShape(Rectangle())
                    .gesture(canvasGesture(canvas: rect.size))
                    .onTapGesture(count: 2) { withAnimation { viewScale = 1; viewOffset = .zero } }
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
            CaptureFlow(kind: c.kind, picked: c.picked, canvasAspect: session.canvasAspect) { layer in
                capture = nil
                if let layer {
                    session.add(layer)
                    transformOn = layer.kind == .reference  // place a new reference straight away
                }
            }
        }
        .photosPicker(isPresented: $showPhotos, selection: $photoItem, matching: .images)
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            Task {
                if let data = try? await item.loadTransferable(type: Data.self), let image = UIImage(data: data) {
                    capture = Capture(kind: photosKind, picked: image)
                }
                photoItem = nil
            }
        }
    }

    // MARK: canvas

    private func canvas(size: CGSize) -> some View {
        ZStack {
            Rectangle().fill(Color.white)
            ForEach(session.layers) { layer in
                if layer.isVisible { layerView(layer, canvas: size) }
            }
        }
        .frame(width: size.width, height: size.height)
        .compositingGroup()  // so Multiply blends with the layers below, not the background
        .clipped()
        .overlay {
            if transformOn, let layer = session.selected, layer.kind == .reference {
                let w = layer.width * size.width
                Rectangle()
                    .stroke(Color.blue, lineWidth: 2)
                    .frame(width: w, height: w / layer.aspect)
                    .rotationEffect(layer.rotation)
                    .position(x: layer.center.x * size.width, y: layer.center.y * size.height)
                    .allowsHitTesting(false)
            }
        }
        .shadow(color: .black.opacity(0.4), radius: 12, y: 4)
    }

    @ViewBuilder
    private func layerView(_ layer: Layer, canvas: CGSize) -> some View {
        if layer.kind == .canvas {
            Image(uiImage: layer.image)
                .resizable()
                .frame(width: canvas.width, height: canvas.height)
                .opacity(layer.opacity)
                .blendMode(layer.blend.mode)
        } else {
            let w = layer.width * canvas.width
            Image(uiImage: layer.image)
                .resizable()
                .frame(width: w, height: w / layer.aspect)
                .rotationEffect(layer.rotation)
                .position(x: layer.center.x * canvas.width, y: layer.center.y * canvas.height)
                .opacity(layer.opacity)
                .blendMode(layer.blend.mode)
        }
    }

    /// Transform on: one finger moves the reference, pinch scales, twist rotates.
    /// Transform off: the same gestures pan and zoom the view; double-tap fits.
    private func canvasGesture(canvas: CGSize) -> some Gesture {
        SimultaneousGesture(SimultaneousGesture(DragGesture(), MagnifyGesture()), RotateGesture())
            .onChanged { value in
                let drag = value.first?.first, magnify = value.first?.second, rotate = value.second
                if let layer = session.selected, transformOn, layer.kind == .reference {
                    if gestureStart == nil {
                        gestureStart = (layer.center, layer.width, layer.rotation, viewScale, viewOffset)
                    }
                    guard let start = gestureStart else { return }
                    if let drag {
                        layer.center = CGPoint(x: start.center.x + drag.translation.width / (canvas.width * viewScale),
                                               y: start.center.y + drag.translation.height / (canvas.height * viewScale))
                    }
                    if let magnify { layer.width = max(0.03, start.width * magnify.magnification) }
                    if let rotate { layer.rotation = start.rotation + rotate.rotation }
                } else {
                    if gestureStart == nil {
                        gestureStart = (.zero, 0, .zero, viewScale, viewOffset)
                    }
                    guard let start = gestureStart else { return }
                    if let drag {
                        viewOffset = CGSize(width: start.offset.width + drag.translation.width,
                                            height: start.offset.height + drag.translation.height)
                    }
                    if let magnify { viewScale = min(max(start.scale * magnify.magnification, 0.5), 8) }
                }
            }
            .onEnded { _ in gestureStart = nil }
    }

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
                LookBar(layer: layer, transformOn: $transformOn, canvasAspect: session.canvasAspect)
                    .padding(.bottom, 12)
            }
        }
    }

    private var topBar: some View {
        HStack {
            Text("Transfer test").font(.headline)
            Spacer()
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
            toolButton("camera", "Camera") { capture = Capture(kind: session.nextKind, picked: nil) }
            Menu {
                Button("Reference from Photos") { photosKind = .reference; showPhotos = true }
                Button("Canvas photo from Photos") { photosKind = .canvas; showPhotos = true }
            } label: {
                toolIcon("photo.on.rectangle", on: false)
            }
            .accessibilityLabel("Photos")
            toolButton("arrow.up.and.down.and.arrow.left.and.right", "Transform", on: transformOn) {
                transformOn.toggle()
            }
            .disabled(session.selected?.kind != .reference)
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
                    if layer.kind != .reference { transformOn = false }
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

/// The selected layer's Look, cut down: opacity first and largest, blend, and
/// for a reference, Transform and Fit.
struct LookBar: View {
    @Bindable var layer: Layer
    @Binding var transformOn: Bool
    let canvasAspect: CGFloat

    var body: some View {
        HStack(spacing: 16) {
            Text(layer.name).font(.subheadline.weight(.semibold)).lineLimit(1).frame(maxWidth: 140, alignment: .leading)
            Text("Opacity")
            Slider(value: $layer.opacity, in: 0...1).frame(width: 240)
            Text("\(Int((layer.opacity * 100).rounded()))%").monospacedDigit().frame(width: 44, alignment: .trailing)
            Picker("Blend", selection: $layer.blend) {
                ForEach(Blend.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)
            if layer.kind == .reference {
                Toggle("Transform", isOn: $transformOn).toggleStyle(.button)
                Button("Fit") { layer.fit(canvasAspect: canvasAspect) }
            }
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }
}
