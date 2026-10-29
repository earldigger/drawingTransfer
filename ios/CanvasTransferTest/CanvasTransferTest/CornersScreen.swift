import SwiftUI
import UIKit

/// Whether Camera and Adjust corners look for the canvas or paper. Remembered
/// between launches; off starts every photo with its whole frame.
let findRectangleKey = "findRectangle"

/// Adjust corners: drag the four corners onto the canvas or paper. Outside
/// is dimmed, and a loupe shows the corner being dragged.
struct CornersScreen: View {
    let image: UIImage
    var onAdd: (Corners) -> Void
    var onRetake: (() -> Void)?
    var onCancel: () -> Void
    let addTitle: String  // "Add layer", or "Done" when editing a layer's corners

    @AppStorage(findRectangleKey) private var findRectangle = true
    @State private var corners: Corners
    private let detected: Corners?  // nil = no rectangle found
    private let notFound: Corners  // where the corners start when nothing was found
    @State private var dragging: Int? = nil

    /// `notFoundInset`: how far in from the edges the corners start when no
    /// rectangle is found (a camera shot rarely fills the frame exactly).
    /// `start`: corners to begin with, when editing a layer's; otherwise they
    /// come from detection and the Find rectangle setting.
    init(image: UIImage, detected: Corners?, notFoundInset: CGFloat, start: Corners? = nil,
         addTitle: String = "Add layer", onAdd: @escaping (Corners) -> Void,
         onRetake: (() -> Void)?, onCancel: @escaping () -> Void) {
        self.image = image
        self.onAdd = onAdd
        self.onRetake = onRetake
        self.onCancel = onCancel
        self.addTitle = addTitle
        self.detected = detected
        notFound = Corners.inset(image.size, by: notFoundInset)
        let find = UserDefaults.standard.object(forKey: findRectangleKey) as? Bool ?? true
        _corners = State(initialValue: start ?? (find ? detected ?? notFound : Corners.inset(image.size, by: 0)))
    }

    private var wholePhoto: Corners { Corners.inset(image.size, by: 0) }

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
            Text("Keeps its proportions, at Multiply 60 % with auto levels.")
                .font(.footnote).foregroundStyle(.secondary)
            Button("Whole photo", systemImage: "arrow.up.left.and.arrow.down.right") { corners = wholePhoto }
            Button("Detected outline", systemImage: "viewfinder") { corners = detected ?? notFound }
                .disabled(detected == nil)
            if findRectangle && detected == nil {
                Text("No rectangle found in this photo.").font(.footnote).foregroundStyle(.secondary)
            }
            Divider()
            Toggle("Find rectangle automatically", isOn: $findRectangle)
                .onChange(of: findRectangle) { _, on in corners = on ? detected ?? notFound : wholePhoto }
            Text("Off: every photo starts with the whole frame, and Camera shows no outline.")
                .font(.footnote).foregroundStyle(.secondary)
            Spacer()
            Button {
                onAdd(corners)
            } label: {
                Text(addTitle).frame(maxWidth: .infinity).padding(.vertical, 6)
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

    @State private var photo: UIImage? = nil
    @State private var detected: Corners? = nil

    private var fromPhotos: Bool { picked != nil }

    var body: some View {
        Group {
            if let photo {
                // A picked photo is often already flat, so with nothing found it
                // starts whole; a camera shot starts 10 % in from the edges.
                CornersScreen(image: photo, detected: detected, notFoundInset: fromPhotos ? 0 : 0.1, onAdd: add,
                              onRetake: fromPhotos ? nil : { self.photo = nil; self.detected = nil },
                              onCancel: { onDone(nil) })
            } else if !fromPhotos {
                CameraScreen(onPhoto: { taken in
                    (photo, detected) = Self.prepare(taken)
                }, onCancel: { onDone(nil) })
            } else {
                Color.black
            }
        }
        .onAppear {
            if let picked, photo == nil {
                (photo, detected) = Self.prepare(picked)
            }
        }
    }

    /// Upright pixels, and the rectangle found in them, if any. Detection always
    /// runs, so turning it on in Adjust corners has an outline to show.
    private static func prepare(_ image: UIImage) -> (UIImage, Corners?) {
        let upright = ImageOps.prepared(image)
        return (upright, ImageOps.detectRectangle(in: upright))
    }

    private func add(_ corners: Corners) {
        guard let photo else { return }
        let image = ImageOps.layerImage(from: photo, corners: corners)
        let layer = Layer(name: "Image", image: image, canvasAspect: canvasAspect)
        layer.source = photo  // kept, so Edit corners can change them later
        layer.sourceID = UUID()
        layer.corners = corners
        onDone(layer)
    }
}
