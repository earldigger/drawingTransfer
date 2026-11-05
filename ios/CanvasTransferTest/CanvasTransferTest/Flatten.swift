import SwiftUI
import UIKit

/// Flatten: the visible layers, exactly as the canvas shows them (opacity,
/// blend, Look, crop, transform), rendered into one new, ordinary layer, so
/// Pick, Simplify and Highlight can read what you see.
extension TransferSession {
    /// The visible layers into a new "Flattened n" on top, at Normal 100 %,
    /// filling the canvas; the layers that went into it are hidden, not
    /// deleted, and the new one is selected. One undo step. False if
    /// nothing is visible or rendering failed.
    @discardableResult @MainActor
    func flattenVisible() -> Bool {
        let sources = layers.filter(\.isVisible).map(\.id)
        guard !sources.isEmpty, let image = Flatten.render(self, layers: Set(sources)) else { return false }
        let layer = Layer(name: "Flattened \(nextFlattenedNumber)", image: image, canvasAspect: canvasAspect)
        layer.opacity = 1
        layer.blend = .normal  // the Look starts at defaults; no auto levels
        layer.quad = Flatten.fullCanvas
        for source in layers where sources.contains(source.id) { source.isVisible = false }
        add(layer)  // on top, and selected
        return true
    }

    /// One more than the highest "Flattened n" there is.
    var nextFlattenedNumber: Int {
        let numbers = layers.compactMap { layer -> Int? in
            guard layer.name.hasPrefix("Flattened ") else { return nil }
            return Int(layer.name.dropFirst("Flattened ".count))
        }
        return (numbers.max() ?? 0) + 1
    }
}

enum Flatten {
    static let longEdge: CGFloat = ImageOps.maxEdge  // 3000 px, the same limit as photos

    /// Fills the canvas exactly: the image has the canvas's proportions.
    static let fullCanvas = [CGPoint(x: 0, y: 0), CGPoint(x: 1, y: 0), CGPoint(x: 1, y: 1), CGPoint(x: 0, y: 1)]

    /// `layers` drawn exactly as on the canvas, on its white, without the
    /// grid, at the canvas's proportions with a long edge of `longEdge`.
    @MainActor
    static func render(_ session: TransferSession, layers: Set<UUID>) -> UIImage? {
        let aspect = session.canvasAspect
        let points = aspect >= 1 ? CGSize(width: 1000, height: (1000 / aspect).rounded())
                                 : CGSize(width: (1000 * aspect).rounded(), height: 1000)
        let renderer = ImageRenderer(content: CanvasContent(layers: session.layers, size: points, only: layers,
                                                            background: session.background.color))
        renderer.scale = longEdge / max(points.width, points.height)
        renderer.isOpaque = true
        guard let cg = renderer.cgImage else { return nil }
        return UIImage(cgImage: cg)  // scale 1: its size is its pixels, as photos are
    }
}
