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
    let id: UUID
    var name: String
    let image: UIImage  // corrected and ready to show
    var opacity = 0.6
    var blend = Blend.multiply  // white paper disappears
    var isVisible = true
    // Where the image sits, in fractions of the canvas: its center, its
    // width, and its rotation.
    var center = CGPoint(x: 0.5, y: 0.5)
    var width: CGFloat = 1
    var rotation: Angle = .zero
    var crop = Crop.full  // the part of the image that shows, in fractions of it
    var adjustments = Adjustments() {
        didSet { if adjustments != oldValue { refreshShownImage() } }
    }
    /// `image` with the adjustments applied; what the canvas draws. Made on the
    /// GPU in the background, so it can trail a slider by a frame or two.
    private(set) var shownImage: UIImage
    @ObservationIgnored private var rendering = false
    @ObservationIgnored private var renderAgain = false

    /// Largest width, in canvas widths: room to zoom into a small part of a
    /// reference, while keeping the image a size the iPad can draw.
    static let maxWidth: CGFloat = 12

    init(id: UUID = UUID(), name: String, image: UIImage, canvasAspect: CGFloat) {
        self.id = id
        self.name = name
        self.image = image
        shownImage = image
        fit(canvasAspect: canvasAspect)
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
            if adjustments == wanted { shownImage = adjusted ?? image }
            if renderAgain {
                renderAgain = false
                refreshShownImage()
            }
        }
    }

    var aspect: CGFloat { image.size.width / max(image.size.height, 1) }

    var placementDescription: String {
        String(format: "center %.3f, %.3f  width %.3f  rotation %.1f°", center.x, center.y, width, rotation.degrees)
    }

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
    var grid = GridSettings()

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
