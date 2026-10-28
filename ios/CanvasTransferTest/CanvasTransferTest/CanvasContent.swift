import SwiftUI
import UIKit

/// What's on the canvas: white, the layers bottom to top, and the grid. The
/// workspace shows it, and Share renders it at full resolution, so the
/// exported image is what you see.
struct CanvasContent: View {
    let layers: [Layer]
    let size: CGSize
    var grid: GridSettings? = nil  // nil = no grid
    var gridLineWidth: CGFloat = 1.5
    var faintFullImageOf: UUID? = nil  // the layer being cropped: its whole image shows faintly too

    var body: some View {
        ZStack {
            Rectangle().fill(Color.white)
            ForEach(layers) { layer in
                if layer.isVisible { layerView(layer) }
            }
            if let grid { GridLines(grid: grid, lineWidth: gridLineWidth) }
        }
        .frame(width: size.width, height: size.height)
        .clipped()  // first, so the group below is only ever canvas-sized
        .compositingGroup()  // so Multiply blends with the layers below, not the background
    }

    /// The layer's image, clipped to its crop. While it is being cropped, the
    /// whole image also shows faintly underneath, so you see what's cut off.
    @ViewBuilder
    private func layerView(_ layer: Layer) -> some View {
        let w = layer.width * size.width, h = w / layer.aspect, c = layer.crop
        let image = Image(uiImage: layer.image).resizable().frame(width: w, height: h)
        if faintFullImageOf == layer.id {
            placed(image, layer, opacity: layer.opacity * 0.3)
        }
        // Clipped, not masked: a mask is drawn offscreen at the image's full
        // size, and past the iPad's texture limit a large image vanished.
        let cropped = image
            .offset(x: -c.minX * w, y: -c.minY * h)
            .frame(width: c.width * w, height: c.height * h, alignment: .topLeading)
            .clipped()
            .offset(x: c.minX * w, y: c.minY * h)
            .frame(width: w, height: h, alignment: .topLeading)
        placed(cropped, layer, opacity: layer.opacity)
    }

    private func placed(_ content: some View, _ layer: Layer, opacity: Double) -> some View {
        content
            .rotationEffect(layer.rotation)
            .position(x: layer.center.x * size.width, y: layer.center.y * size.height)
            .opacity(opacity)
            .blendMode(layer.blend.mode)
    }
}

/// Evenly spaced lines; the canvas edges aren't drawn.
struct GridLines: View {
    let grid: GridSettings
    let lineWidth: CGFloat

    var body: some View {
        Canvas { context, size in
            var lines = Path()
            for i in 1..<max(grid.columns, 1) {
                let x = size.width * CGFloat(i) / CGFloat(grid.columns)
                lines.move(to: CGPoint(x: x, y: 0))
                lines.addLine(to: CGPoint(x: x, y: size.height))
            }
            for i in 1..<max(grid.rows, 1) {
                let y = size.height * CGFloat(i) / CGFloat(grid.rows)
                lines.move(to: CGPoint(x: 0, y: y))
                lines.addLine(to: CGPoint(x: size.width, y: y))
            }
            context.stroke(lines, with: .color(grid.color.color.opacity(grid.opacity)), lineWidth: lineWidth)
        }
        .allowsHitTesting(false)
    }
}

/// The canvas as a full-resolution JPEG, for the share sheet.
enum CanvasExport {
    static let longEdgeRange: ClosedRange<CGFloat> = 2048...6000  // pixels

    /// As many pixels as the sharpest visible layer has across the canvas,
    /// within `longEdgeRange`.
    static func pixelSize(_ session: TransferSession) -> CGSize {
        let aspect = session.canvasAspect
        let perCanvasWidth = session.layers.filter(\.isVisible)
            .map { $0.image.size.width * $0.image.scale / max($0.width, 0.01) }
            .max() ?? longEdgeRange.lowerBound
        let size = CGSize(width: perCanvasWidth, height: perCanvasWidth / aspect)
        let longEdge = max(size.width, size.height)
        let factor = min(max(longEdge, longEdgeRange.lowerBound), longEdgeRange.upperBound) / longEdge
        return CGSize(width: (size.width * factor).rounded(), height: (size.height * factor).rounded())
    }

    /// Renders the canvas and writes it to a temporary file named for the
    /// canvas size and the time. Nil if rendering fails.
    @MainActor
    static func render(_ session: TransferSession, withGrid: Bool) -> URL? {
        let pixels = pixelSize(session)
        let points = CGSize(width: 1000, height: (1000 / session.canvasAspect).rounded())
        let content = CanvasContent(layers: session.layers, size: points,
                                    grid: withGrid ? session.grid : nil,
                                    gridLineWidth: max(points.width, points.height) * 0.0015)
        let renderer = ImageRenderer(content: content)
        renderer.scale = pixels.width / points.width
        guard let image = renderer.uiImage, let jpeg = image.jpegData(compressionQuality: 0.95) else { return nil }

        let inches = "\(Int(session.canvasSize.width))x\(Int(session.canvasSize.height)) in"
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd HH.mm"  // sorts by date in Finder
        let time = formatter.string(from: Date())
        let url = URL.temporaryDirectory.appending(path: "Transfer \(inches)\(withGrid ? " grid" : "") \(time).jpg")
        do {
            try jpeg.write(to: url, options: .atomic)
            return url
        } catch {
            return nil
        }
    }
}

/// The iPad share sheet.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    var onDone: () -> Void

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        controller.completionWithItemsHandler = { _, _, _, _ in onDone() }
        return controller
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
