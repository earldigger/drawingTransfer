import SwiftUI
import UIKit

/// Adjust corners: drag the four corners onto the canvas or paper. Outside
/// is dimmed, and a loupe shows the corner being dragged.
struct CornersScreen: View {
    let image: UIImage
    @Binding var kind: LayerKind
    var onAdd: (Corners) -> Void
    var onRetake: (() -> Void)?
    var onCancel: () -> Void

    @State private var corners: Corners
    private let detected: Corners
    @State private var dragging: Int? = nil

    init(image: UIImage, corners: Corners, kind: Binding<LayerKind>, onAdd: @escaping (Corners) -> Void,
         onRetake: (() -> Void)?, onCancel: @escaping () -> Void) {
        self.image = image
        _kind = kind
        self.onAdd = onAdd
        self.onRetake = onRetake
        self.onCancel = onCancel
        _corners = State(initialValue: corners)
        detected = corners
    }

    var body: some View {
        HStack(spacing: 0) {
            GeometryReader { geo in
                let rect = fitRect(image.size, in: geo.size, margin: 28)
                let scale = rect.width / max(image.size.width, 1)
                let points = corners.points.map { CGPoint(x: rect.minX + $0.x * scale, y: rect.minY + $0.y * scale) }
                ZStack(alignment: .topLeading) {
                    Image(uiImage: image)
                        .resizable()
                        .frame(width: rect.width, height: rect.height)
                        .position(x: rect.midX, y: rect.midY)
                    Path { p in
                        p.addRect(rect)
                        p.addLines(points)
                        p.closeSubpath()
                    }
                    .fill(Color.black.opacity(0.5), style: FillStyle(eoFill: true))
                    Path { p in
                        p.addLines(points)
                        p.closeSubpath()
                    }
                    .stroke(Color.blue, lineWidth: 2)
                    ForEach(0..<4, id: \.self) { i in
                        Circle()
                            .fill(Color.white.opacity(dragging == i ? 1 : 0.3))
                            .overlay(Circle().stroke(Color.blue, lineWidth: 3))
                            .frame(width: 30, height: 30)
                            .contentShape(Circle().inset(by: -8))  // 46 pt to touch
                            .position(points[i])
                            .gesture(
                                DragGesture(minimumDistance: 0, coordinateSpace: .named("photo"))
                                    .onChanged { value in
                                        dragging = i
                                        let x = (value.location.x - rect.minX) / scale
                                        let y = (value.location.y - rect.minY) / scale
                                        corners.points[i] = CGPoint(x: min(max(x, 0), image.size.width),
                                                                    y: min(max(y, 0), image.size.height))
                                    }
                                    .onEnded { _ in dragging = nil }
                            )
                    }
                    if let i = dragging {
                        loupe(at: points[i], rect: rect)
                            .position(x: points[i].x, y: max(points[i].y - 120, 70))
                    }
                }
                .coordinateSpace(.named("photo"))
            }
            .background(Color(white: 0.09))

            sidePanel
        }
        .background(Color(white: 0.09).ignoresSafeArea())
    }

    private func loupe(at point: CGPoint, rect: CGRect) -> some View {
        let zoom: CGFloat = 3, size: CGFloat = 132
        return ZStack {
            Image(uiImage: image)
                .resizable()
                .frame(width: rect.width * zoom, height: rect.height * zoom)
                .position(x: size / 2 + rect.width * zoom / 2 - (point.x - rect.minX) * zoom,
                          y: size / 2 + rect.height * zoom / 2 - (point.y - rect.minY) * zoom)
            Path { p in
                p.move(to: CGPoint(x: size / 2, y: 6)); p.addLine(to: CGPoint(x: size / 2, y: size - 6))
                p.move(to: CGPoint(x: 6, y: size / 2)); p.addLine(to: CGPoint(x: size - 6, y: size / 2))
            }
            .stroke(Color.blue, lineWidth: 1.5)
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay(Circle().stroke(Color.white, lineWidth: 3))
        .shadow(radius: 8)
        .allowsHitTesting(false)
    }

    private var sidePanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                if let onRetake { Button("Retake", action: onRetake) }
                Spacer()
                Button("Cancel", action: onCancel).foregroundStyle(.secondary)
            }
            Text("Adjust corners").font(.headline)
            Text("Use as").font(.caption).foregroundStyle(.secondary)
            Picker("Use as", selection: $kind) {
                ForEach(LayerKind.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            Text(kind == .canvas
                 ? "Fills the canvas exactly, at Normal 100 %. No auto levels."
                 : "Keeps its proportions, at Multiply 60 % with auto levels.")
                .font(.footnote).foregroundStyle(.secondary)
            Button("Reset to detected") { corners = detected }
            Spacer()
            Button {
                onAdd(corners)
            } label: {
                Text("Add layer").frame(maxWidth: .infinity).padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(20)
        .frame(width: 300)
        .background(Color(white: 0.13))
        .environment(\.colorScheme, .dark)
    }
}

/// One photo from Camera or Photos, through Adjust corners, to a new layer.
struct CaptureFlow: View {
    let canvasAspect: CGFloat
    let picked: UIImage?  // from Photos; nil = take one with the camera
    var onDone: (Layer?) -> Void

    @State private var kind: LayerKind
    @State private var photo: UIImage? = nil
    @State private var corners: Corners? = nil

    init(kind: LayerKind, picked: UIImage?, canvasAspect: CGFloat, onDone: @escaping (Layer?) -> Void) {
        self.canvasAspect = canvasAspect
        self.picked = picked
        self.onDone = onDone
        _kind = State(initialValue: kind)
    }

    private var fromPhotos: Bool { picked != nil }

    var body: some View {
        Group {
            if let photo, let corners {
                CornersScreen(image: photo, corners: corners, kind: $kind, onAdd: add,
                              onRetake: fromPhotos ? nil : { self.photo = nil; self.corners = nil },
                              onCancel: { onDone(nil) })
            } else if !fromPhotos {
                CameraScreen(kind: $kind, onPhoto: { taken in
                    let (image, found) = Self.prepare(taken, fromPhotos: false)
                    photo = image
                    corners = found
                }, onCancel: { onDone(nil) })
            } else {
                Color.black
            }
        }
        .onAppear {
            if let picked, photo == nil {
                let (image, found) = Self.prepare(picked, fromPhotos: true)
                photo = image
                corners = found
            }
        }
    }

    /// Upright pixels and starting corners: the detected rectangle if there is
    /// one; otherwise the whole image for a picked photo (often already flat),
    /// or 10 % in from the edges for a camera shot.
    private static func prepare(_ image: UIImage, fromPhotos: Bool) -> (UIImage, Corners) {
        let upright = ImageOps.prepared(image)
        let corners = ImageOps.detectRectangle(in: upright)
            ?? Corners.inset(upright.size, by: fromPhotos ? 0 : 0.1)
        return (upright, corners)
    }

    private func add(_ corners: Corners) {
        guard let photo else { return }
        let image = ImageOps.layerImage(from: photo, corners: corners, kind: kind)
        let name = kind == .canvas ? "Canvas · \(Date().formatted(.dateTime.month(.abbreviated).day()))" : "Reference"
        onDone(Layer(kind: kind, name: name, image: image, canvasAspect: canvasAspect))
    }
}
