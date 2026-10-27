import Observation
import SwiftUI
import UIKit

/// What a layer is for. Names follow docs/design/README.md.
enum LayerKind: String, CaseIterable, Identifiable {
    case canvas = "Canvas"  // a photo of the real canvas, corrected to fill it exactly
    case reference = "Reference"  // the photo or drawing being transferred

    var id: String { rawValue }
}

enum Blend: String, CaseIterable, Identifiable {
    case normal = "Normal"
    case multiply = "Multiply"

    var id: String { rawValue }
    var mode: BlendMode { self == .multiply ? .multiply : .normal }
}

/// Four corners in a photo's pixels (origin top-left), in the order
/// top-left, top-right, bottom-right, bottom-left.
struct Corners: Equatable {
    var points: [CGPoint]

    static func inset(_ size: CGSize, by fraction: CGFloat) -> Corners {
        let dx = size.width * fraction, dy = size.height * fraction
        return Corners(points: [
            CGPoint(x: dx, y: dy), CGPoint(x: size.width - dx, y: dy),
            CGPoint(x: size.width - dx, y: size.height - dy), CGPoint(x: dx, y: size.height - dy),
        ])
    }
}

@Observable
final class Layer: Identifiable {
    let id = UUID()
    let kind: LayerKind
    var name: String
    let image: UIImage  // corrected and ready to show
    var opacity: Double
    var blend: Blend
    var isVisible = true
    // Where a reference sits, in fractions of the canvas: its center, its
    // width, and its rotation. A canvas photo always fills the canvas.
    var center = CGPoint(x: 0.5, y: 0.5)
    var width: CGFloat = 1
    var rotation: Angle = .zero

    /// A new layer starts with its kind's look: a reference at Multiply 60 %
    /// (white paper disappears), a canvas photo at Normal 100 %.
    init(kind: LayerKind, name: String, image: UIImage, canvasAspect: CGFloat) {
        self.kind = kind
        self.name = name
        self.image = image
        opacity = kind == .canvas ? 1 : 0.6
        blend = kind == .canvas ? .normal : .multiply
        fit(canvasAspect: canvasAspect)
    }

    var aspect: CGFloat { image.size.width / max(image.size.height, 1) }

    /// Largest placement inside the canvas, centered, never cropped.
    func fit(canvasAspect: CGFloat) {
        center = CGPoint(x: 0.5, y: 0.5)
        width = aspect >= canvasAspect ? 1 : aspect / canvasAspect
        rotation = .zero
    }
}

@Observable
final class TransferSession {
    static let canvasSizes: [CGSize] = [
        CGSize(width: 8, height: 10), CGSize(width: 9, height: 12), CGSize(width: 11, height: 14),
        CGSize(width: 12, height: 16), CGSize(width: 16, height: 20), CGSize(width: 18, height: 24),
        CGSize(width: 24, height: 30), CGSize(width: 24, height: 36), CGSize(width: 30, height: 40),
        CGSize(width: 36, height: 48),
    ]

    var canvasSize = CGSize(width: 16, height: 20)  // inches, portrait
    var layers: [Layer] = []  // bottom to top
    var selectedID: UUID?

    var canvasAspect: CGFloat { canvasSize.width / canvasSize.height }
    var selected: Layer? { layers.first { $0.id == selectedID } }

    /// What Camera offers first: a canvas photo until there is one, then a
    /// reference until there is one, then canvas photos as the painting goes on.
    var nextKind: LayerKind {
        if !layers.contains(where: { $0.kind == .canvas }) { return .canvas }
        if !layers.contains(where: { $0.kind == .reference }) { return .reference }
        return .canvas
    }

    /// References go on top; a canvas photo goes just under the lowest reference.
    func add(_ layer: Layer) {
        if layer.kind == .canvas, let index = layers.firstIndex(where: { $0.kind == .reference }) {
            layers.insert(layer, at: index)
        } else {
            layers.append(layer)
        }
        selectedID = layer.id
    }

    func delete(_ layer: Layer) {
        layers.removeAll { $0.id == layer.id }
        if selectedID == layer.id { selectedID = layers.last?.id }
    }
}

/// The largest rectangle of `size`'s proportions centered in `bounds`, inset by `margin`.
func fitRect(_ size: CGSize, in bounds: CGSize, margin: CGFloat = 0) -> CGRect {
    let w = max(bounds.width - 2 * margin, 1), h = max(bounds.height - 2 * margin, 1)
    let s = min(w / max(size.width, 1), h / max(size.height, 1))
    let fw = size.width * s, fh = size.height * s
    return CGRect(x: (bounds.width - fw) / 2, y: (bounds.height - fh) / 2, width: fw, height: fh)
}
