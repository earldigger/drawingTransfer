import Observation
import SwiftUI
import UIKit

enum Blend: String, CaseIterable, Identifiable, Codable {
    case normal = "Normal"
    case multiply = "Multiply"  // white disappears: for drawings on paper
    case screen = "Screen"  // black disappears: for light lines on a dark ground

    var id: String { rawValue }
    var mode: BlendMode {
        switch self {
        case .normal: .normal
        case .multiply: .multiply
        case .screen: .screen
        }
    }
}

/// Four corners in a photo's pixels (origin top-left), in the order
/// top-left, top-right, bottom-right, bottom-left.
struct Corners: Codable, Equatable {
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
    let id: UUID
    var name: String
    private(set) var image: UIImage  // corrected and ready to show
    /// Names the image's file and its undo copy; new whenever Edit corners
    /// remakes the image. A layer from before that is named by its own id.
    private(set) var imageID: UUID
    // The upright photo the image was corrected from, and the corners used,
    // in its pixels, so Edit corners can start where you left off. Nil for
    // layers added before photos were kept.
    var source: UIImage? = nil
    var sourceID: UUID? = nil  // names its file; shared by duplicates
    var corners: Corners? = nil
    /// For a flattened layer, the layers it was last rendered from; nil for
    /// any other layer. (It has no photo, so no Edit corners.)
    var flattenedFrom: [UUID]? = nil
    var isFlattened: Bool { flattenedFrom != nil }
    var opacity = 0.6
    var blend = Blend.multiply  // white paper disappears
    var isVisible = true
    /// Where the image's own corners land, [top-left, top-right, bottom-right,
    /// bottom-left], in fractions of the canvas's width and height, as in the
    /// prototype. Moving, scaling, rotating, flipping, skewing and distorting
    /// all just move these; the image is drawn into them.
    var quad: [CGPoint] = [CGPoint(x: 0, y: 0), CGPoint(x: 1, y: 0), CGPoint(x: 1, y: 1), CGPoint(x: 0, y: 1)]
    var crop = Crop.full  // the part of the image that shows, in fractions of it
    var adjustments = Adjustments() {
        didSet { if adjustments != oldValue { refreshShownImage() } }
    }
    /// `image` with the adjustments applied; what the canvas draws. Made on the
    /// GPU in the background, so it can trail a slider by a frame or two.
    private(set) var shownImage: UIImage
    @ObservationIgnored private var rendering = false
    @ObservationIgnored private var renderAgain = false
    @ObservationIgnored private var pixelCache: (image: UIImage, pixels: PixelBuffer)? = nil

    /// The shown image's pixels, for Pick; read once per image.
    func pixels() -> PixelBuffer? {
        if let cache = pixelCache, cache.image === shownImage { return cache.pixels }
        guard let pixels = PixelBuffer(shownImage) else { return nil }
        pixelCache = (shownImage, pixels)
        return pixels
    }

    /// Largest and smallest top edge, in canvas widths: room to zoom into a
    /// small part of a reference, while keeping the image a size the iPad can draw.
    static let maxWidth: CGFloat = 12
    static let minWidth: CGFloat = 0.03

    init(id: UUID = UUID(), name: String, image: UIImage, imageID: UUID? = nil, canvasAspect: CGFloat) {
        self.id = id
        self.name = name
        self.image = image
        self.imageID = imageID ?? id
        shownImage = image
        fit(canvasAspect: canvasAspect)
    }

    /// A new image for the layer (Edit corners, or undoing it). Placement,
    /// crop and adjustments stay; the height follows the new proportions.
    func replaceImage(_ image: UIImage, id: UUID = UUID()) {
        self.image = image
        imageID = id
        refreshShownImage()
    }

    /// Remakes the image from `source` with new corners, as Add layer does.
    /// It keeps its center, width, rotation and flips; its height follows the
    /// new proportions, so a skew or distortion starts over.
    func applyCorners(_ newCorners: Corners, canvasAspect: CGFloat) {
        guard let source else { return }
        corners = newCorners
        let canvas = CGSize(width: canvasAspect, height: 1)
        let q = quadPoints(in: canvas)
        let u = q[1] - q[0], v = q[3] - q[0]
        replaceImage(ImageOps.layerImage(from: source, corners: newCorners))
        guard hypot(u.x, u.y) > 1e-9 else { return }
        let side: CGFloat = QuadGeometry.cross(u, v) >= 0 ? 1 : -1  // which way the image faces
        let down = CGPoint(x: -u.y, y: u.x) * (side / aspect)  // across the top edge, image-proportioned
        let tl = QuadGeometry.centroid(q) - (u + down) * 0.5
        setQuad(points: [tl, tl + u, tl + u + down, tl + down], in: canvas)
    }

    /// One render at a time, always of the latest adjustments: while a
    /// slider moves, changes that arrive during a render are folded into the next.
    private func refreshShownImage() {
        guard !adjustments.isIdentity else {
            shownImage = image
            return
        }
        guard !rendering else {
            renderAgain = true
            return
        }
        rendering = true
        let image = self.image, wanted = adjustments
        Task { @MainActor in
            let adjusted = await Task.detached(priority: .userInitiated) { Look.adjusted(image, wanted) }.value
            rendering = false
            if adjustments == wanted && self.image === image { shownImage = adjusted ?? image }
            else if self.image !== image { renderAgain = true }  // the image changed while rendering
            if renderAgain {
                renderAgain = false
                refreshShownImage()
            }
        }
    }

    var aspect: CGFloat { image.size.width / max(image.size.height, 1) }

    var placementDescription: String {
        quad.map { String(format: "(%.3f, %.3f)", $0.x, $0.y) }.joined(separator: " ")
    }

    // MARK: placement

    func quadPoints(in canvas: CGSize) -> [CGPoint] {
        quad.map { CGPoint(x: $0.x * canvas.width, y: $0.y * canvas.height) }
    }

    func setQuad(points: [CGPoint], in canvas: CGSize) {
        guard points.count == 4, points.allSatisfy({ $0.x.isFinite && $0.y.isFinite }) else { return }
        quad = points.map { CGPoint(x: $0.x / max(canvas.width, 1e-9), y: $0.y / max(canvas.height, 1e-9)) }
    }

    /// The image's top edge, in canvas widths.
    func topEdge(in canvas: CGSize) -> CGFloat {
        let q = quadPoints(in: canvas)
        return hypot(q[1].x - q[0].x, q[1].y - q[0].y) / max(canvas.width, 1e-9)
    }

    /// Moves by `d`, in fractions of the canvas. The center stays within half
    /// a canvas of the edges, so the image can't be lost.
    func move(by d: CGPoint) {
        let c = QuadGeometry.centroid(quad)
        let to = CGPoint(x: min(max(c.x + d.x, -0.5), 1.5), y: min(max(c.y + d.y, -0.5), 1.5))
        quad = QuadGeometry.translate(quad, by: to - c)
    }

    /// Scales about the center, keeping the top edge between `minWidth` and `maxWidth`.
    func scale(by s: CGFloat, in canvas: CGSize) {
        let edge = topEdge(in: canvas)
        guard edge > 1e-9 else { return }
        let clamped = min(max(edge * s, Layer.minWidth), Layer.maxWidth) / edge
        let q = quadPoints(in: canvas)
        setQuad(points: QuadGeometry.scale(q, by: clamped, about: QuadGeometry.centroid(q)), in: canvas)
    }

    func rotate(by angle: Angle, in canvas: CGSize) {
        let q = quadPoints(in: canvas)
        setQuad(points: QuadGeometry.rotate(q, by: angle.radians, about: QuadGeometry.centroid(q)), in: canvas)
    }

    /// Mirrors the image inside the same corners; the crop flips with it.
    func flipHorizontal() { quad = QuadGeometry.flipHorizontal(quad) }
    func flipVertical() { quad = QuadGeometry.flipVertical(quad) }

    /// Largest placement inside the canvas, centered, upright, never cropped.
    func fit(canvasAspect: CGFloat) {
        let width = aspect >= canvasAspect ? 1 : aspect / canvasAspect
        quad = Layer.rectangle(center: CGPoint(x: 0.5, y: 0.5), width: width, rotation: 0,
                               flipH: false, flipV: false, imageAspect: aspect, canvasAspect: canvasAspect)
    }

    /// A plain placement as a quad: what center, width (in canvas widths),
    /// rotation and flips meant before the quad. Opens older sessions.
    static func rectangle(center: CGPoint, width: CGFloat, rotation: Double, flipH: Bool, flipV: Bool,
                          imageAspect: CGFloat, canvasAspect: CGFloat) -> [CGPoint] {
        let c = CGPoint(x: center.x * canvasAspect, y: center.y)  // in canvas heights, the same units both ways
        let w = width * canvasAspect, h = w / max(imageAspect, 1e-6)
        var q = [CGPoint(x: c.x - w / 2, y: c.y - h / 2), CGPoint(x: c.x + w / 2, y: c.y - h / 2),
                 CGPoint(x: c.x + w / 2, y: c.y + h / 2), CGPoint(x: c.x - w / 2, y: c.y + h / 2)]
        if flipH { q = QuadGeometry.flipHorizontal(q) }
        if flipV { q = QuadGeometry.flipVertical(q) }
        q = QuadGeometry.rotate(q, by: rotation, about: c)
        return q.map { CGPoint(x: $0.x / canvasAspect, y: $0.y) }
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
    var grid = GridSettings()
    var swatches: [Swatch] = []  // numbered in this order

    var canvasAspect: CGFloat { canvasSize.width / canvasSize.height }
    var selected: Layer? { layers.first { $0.id == selectedID } }

    /// New images go on top.
    func add(_ layer: Layer) {
        layers.append(layer)
        selectedID = layer.id
    }

    func delete(_ layer: Layer) {
        layers.removeAll { $0.id == layer.id }
        if selectedID == layer.id { selectedID = layers.last?.id }
    }

    /// Moves a layer `by` places up (+) or down (-) the stack, or to `to` (0 = bottom).
    func move(_ layer: Layer, by offset: Int = 0, to place: Int? = nil) {
        guard let i = layers.firstIndex(where: { $0.id == layer.id }) else { return }
        let target = min(max(place ?? i + offset, 0), layers.count - 1)
        guard target != i else { return }
        layers.insert(layers.remove(at: i), at: target)
    }

    /// A copy just above the original, nudged so it shows; selected.
    func duplicate(_ layer: Layer) {
        guard let i = layers.firstIndex(where: { $0.id == layer.id }) else { return }
        let copy = Layer(name: layer.name, image: layer.image, imageID: layer.imageID, canvasAspect: canvasAspect)
        copy.source = layer.source
        copy.sourceID = layer.sourceID
        copy.corners = layer.corners
        copy.flattenedFrom = layer.flattenedFrom
        copy.opacity = layer.opacity
        copy.blend = layer.blend
        copy.isVisible = true
        copy.quad = layer.quad
        copy.move(by: CGPoint(x: 0.03, y: 0.03))
        copy.crop = layer.crop
        copy.adjustments = layer.adjustments
        layers.insert(copy, at: i + 1)
        selectedID = copy.id
    }
}

/// A grid over the canvas for transferring by eye: evenly spaced rows and
/// columns, as in the prototype (`GridSettings` in canvastransfer/models.py).
struct GridSettings: Codable, Equatable {
    static let range = 1...40

    var isOn = false
    var rows = 4
    var columns = 4
    var color = GridColor.red
    var opacity = 0.6

    /// Columns that make the cells as close to square as the rows allow.
    mutating func squareCells(canvasAspect: CGFloat) {
        columns = min(max(Int((CGFloat(rows) * canvasAspect).rounded()), GridSettings.range.lowerBound),
                      GridSettings.range.upperBound)
    }
}

enum GridColor: String, CaseIterable, Codable, Identifiable {
    case red, black, white, blue

    var id: String { rawValue }
    var color: Color {
        switch self {
        case .red: Color(red: 1, green: 40 / 255, blue: 40 / 255)  // the prototype's default
        case .black: .black
        case .white: .white
        case .blue: .blue
        }
    }
}

/// The largest rectangle of `size`'s proportions centered in `bounds`, inset by `margin`.
func fitRect(_ size: CGSize, in bounds: CGSize, margin: CGFloat = 0) -> CGRect {
    let w = max(bounds.width - 2 * margin, 1), h = max(bounds.height - 2 * margin, 1)
    let s = min(w / max(size.width, 1), h / max(size.height, 1))
    let fw = size.width * s, fh = size.height * s
    return CGRect(x: (bounds.width - fw) / 2, y: (bounds.height - fh) / 2, width: fw, height: fh)
}
