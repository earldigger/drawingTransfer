import Observation
import PencilKit
import SwiftUI
import UIKit

/// The Pencil tool. While it's on, strokes are drawn with PencilKit on a
/// clear sheet over the canvas; when another layer is chosen, a layer is
/// added, or the Pencil is put away (turned off, another tool, the Gallery,
/// the app going to the background) the strokes are drawn into a drawing
/// layer: the selected one if it is one, or a new "Drawing n" on top.
/// So a drawing layer is an ordinary image layer, saved like any other.
@Observable
final class PencilController: NSObject, PKCanvasViewDelegate {
    @ObservationIgnored weak var canvasView: PKCanvasView?
    @ObservationIgnored var displaySize: CGSize = .zero  // the canvas on screen, in points
    @ObservationIgnored var scale: CGFloat = 1  // the sheet is drawn this many times larger (see PencilSheet)
    @ObservationIgnored private var strokeSheet: CGSize = .zero  // the sheet's size when these strokes began

    private(set) var hasStrokes = false
    private(set) var canUndo = false
    private(set) var canRedo = false
    /// The last colors chosen, newest first, as #RRGGBB.
    private(set) var recents: [String] = UserDefaults.standard.stringArray(forKey: PencilController.recentsKey) ?? []

    static let recentsCount = 10
    private static let recentsKey = "pencilRecentColors"
    @ObservationIgnored private var strokeCount = 0

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        let count = canvasView.drawing.strokes.count
        if strokeCount == 0 && count > 0 {  // the first stroke: note the sheet it's measured in
            strokeSheet = CGSize(width: displaySize.width / scale, height: displaySize.height / scale)
        }
        strokeCount = count
        hasStrokes = count > 0
        canUndo = canvasView.undoManager?.canUndo ?? false
        canRedo = canvasView.undoManager?.canRedo ?? false
    }

    func undo() { canvasView?.undoManager?.undo() }
    func redo() { canvasView?.undoManager?.redo() }

    /// A color just chosen goes to the front of the history.
    func remember(_ hex: String) {
        recents = Array(([hex] + recents.filter { $0 != hex }).prefix(Self.recentsCount))
        UserDefaults.standard.set(recents, forKey: Self.recentsKey)
    }

    func clearRecents() {
        recents = []
        UserDefaults.standard.removeObject(forKey: Self.recentsKey)
    }

    /// The strokes so far with the sheet size they were drawn on, and a clear
    /// sheet (and no stroke undo) from here on.
    func take() -> (drawing: PKDrawing, sheet: CGSize)? {
        guard let view = canvasView, !view.drawing.strokes.isEmpty else { return nil }
        let drawing = view.drawing
        view.drawing = PKDrawing()
        view.undoManager?.removeAllActions(withTarget: view)
        strokeCount = 0
        hasStrokes = false
        canUndo = false
        canRedo = false
        return (drawing, strokeSheet)
    }
}

/// The sheet the Pencil draws on, with Apple Pencil or a finger. While it's
/// out, the canvas's own finger gestures (pinch, pan, two-finger undo) don't
/// reach the canvas. `scale` above 1 makes the sheet smaller and shows it
/// that much larger, so a stroke can be wider than the ink allows.
struct PencilCanvas: UIViewRepresentable {
    let controller: PencilController
    let tool: PKInkingTool
    let size: CGSize
    let scale: CGFloat

    func makeUIView(context: Context) -> PencilSheet {
        let sheet = PencilSheet()
        let view = sheet.canvas
        view.backgroundColor = .clear
        view.isOpaque = false
        view.isScrollEnabled = false
        view.overrideUserInterfaceStyle = .light  // ink keeps its color; PencilKit lightens dark ink in dark mode
        view.drawingPolicy = .anyInput  // a finger draws too
        view.delegate = controller
        controller.canvasView = view
        return sheet
    }

    func updateUIView(_ sheet: PencilSheet, context: Context) {
        sheet.canvas.tool = tool
        sheet.scale = scale
        controller.displaySize = size
        controller.scale = scale
    }
}

/// Holds the PencilKit canvas, `scale` times smaller than itself and magnified to fit.
final class PencilSheet: UIView {
    let canvas = PKCanvasView()
    var scale: CGFloat = 1 {
        didSet { if scale != oldValue { setNeedsLayout() } }
    }

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .clear
        addSubview(canvas)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override func layoutSubviews() {
        super.layoutSubviews()
        canvas.transform = .identity
        canvas.bounds = CGRect(x: 0, y: 0, width: bounds.width / scale, height: bounds.height / scale)
        canvas.center = CGPoint(x: bounds.midX, y: bounds.midY)
        canvas.transform = CGAffineTransform(scaleX: scale, y: scale)
    }
}

enum Pencil {
    static let longEdge: CGFloat = 2048  // a drawing layer's pixels on its long side
    static let sizes: ClosedRange<Double> = 1...300  // the Pencil's size, in a drawing layer's pixels
    static let pencilInk = PKInkingTool.InkType.pencil

    /// Canvas points per drawing-layer pixel, for sizes given in pixels.
    static func pointsPerPixel(canvas: CGSize) -> CGFloat { pointsPerPixel(canvas) }

    /// How much larger the sheet is shown so a `pixels`-wide stroke fits the
    /// ink's widest, on a canvas `display` points in size on screen.
    static func scale(pixels: Double, display: CGSize, ink: PKInkingTool.InkType = pencilInk) -> CGFloat {
        let points = pixels * pointsPerPixel(display)
        return max(1, ceil(points / ink.validWidthRange.upperBound))
    }

    /// The ink: `pixels` wide in the drawing layer, drawn on the sheet at `scale`.
    static func tool(pixels: Double, color: UIColor, display: CGSize, scale: CGFloat,
                     ink: PKInkingTool.InkType = pencilInk) -> PKInkingTool {
        let width = pixels * pointsPerPixel(display) / scale
        let limits = ink.validWidthRange
        return PKInkingTool(ink, color: color, width: min(max(width, limits.lowerBound), limits.upperBound))
    }

    private static func pointsPerPixel(_ display: CGSize) -> CGFloat {
        display.width > 0 ? max(display.width, display.height) / longEdge : 0.45
    }

    /// A drawing layer: drawn with the Pencil and still filling the canvas as made.
    static func isDrawingLayer(_ layer: Layer) -> Bool {
        layer.name.hasPrefix("Drawing ") && layer.quad == Flatten.fullCanvas && layer.crop == Crop.full
            && layer.adjustments.isIdentity
    }

    /// Draws `drawing` (made on a sheet `sheet` points in size) into the
    /// drawing layer `layerID`, or a new one on top if that isn't one. One undo step.
    @MainActor
    static func commit(_ drawing: PKDrawing, sheet: CGSize, to session: TransferSession, layerID: UUID?) {
        guard sheet.width > 0, sheet.height > 0 else { return }
        let aspect = session.canvasAspect
        let pixels = aspect >= 1 ? CGSize(width: longEdge, height: (longEdge / aspect).rounded())
                                 : CGSize(width: (longEdge * aspect).rounded(), height: longEdge)
        let target = session.layers.first { $0.id == layerID && isDrawingLayer($0) }
        var strokes = UIImage()
        UITraitCollection(userInterfaceStyle: .light).performAsCurrent {  // ink as drawn, not dark-mode inverted
            strokes = drawing.image(from: CGRect(origin: .zero, size: sheet), scale: pixels.width / sheet.width)
        }
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        let rect = CGRect(origin: .zero, size: pixels)
        let image = UIGraphicsImageRenderer(size: pixels, format: format).image { _ in
            target?.image.draw(in: rect)
            strokes.draw(in: rect)
        }
        if let target {
            target.replaceImage(image)
        } else {
            let layer = Layer(name: "Drawing \(nextNumber(session))", image: image, canvasAspect: aspect)
            layer.opacity = 1
            layer.blend = .normal
            layer.quad = Flatten.fullCanvas
            session.add(layer)  // on top, and selected
        }
    }

    /// Erases a stroke (canvas points on a canvas `canvas` points in size)
    /// from any layer, photo or drawing: the stroke is drawn as a mask over the
    /// canvas, the mask is taken back through the layer's corners into its own
    /// picture's pixels (moved, turned, skewed, flipped, all undone), and cut
    /// out of the picture. One undo step.
    @MainActor
    static func erase(_ stroke: EraseStroke, canvas: CGSize, layer: Layer) {
        guard canvas.width > 0, canvas.height > 0, !stroke.points.isEmpty else { return }
        // The mask, over the whole canvas, `k` pixels per canvas point.
        let k = longEdge / max(canvas.width, canvas.height)
        let maskSize = CGSize(width: (canvas.width * k).rounded(), height: (canvas.height * k).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        let mask = UIGraphicsImageRenderer(size: maskSize, format: format).image { context in
            let cg = context.cgContext
            cg.scaleBy(x: k, y: k)
            cg.setStrokeColor(UIColor.black.withAlphaComponent(stroke.opacity).cgColor)
            cg.setLineWidth(stroke.width)
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            cg.addPath(stroke.path.cgPath)
            cg.strokePath()
        }
        // The layer's picture corners in mask pixels, and the mask warped onto the picture.
        let corners = Corners(points: layer.quadPoints(in: canvas).map { CGPoint(x: $0.x * k, y: $0.y * k) })
        let warped = ImageOps.perspectiveCorrect(mask, corners: corners)
        guard warped !== mask else { return }  // couldn't be warped
        let pixels = CGSize(width: layer.image.size.width * layer.image.scale, height: layer.image.size.height * layer.image.scale)
        let rect = CGRect(origin: .zero, size: pixels)
        let image = UIGraphicsImageRenderer(size: pixels, format: format).image { _ in
            layer.image.draw(in: rect)
            warped.draw(in: rect, blendMode: .destinationOut, alpha: 1)  // cut out where the stroke was
        }
        layer.replaceImage(image)
    }

    /// A new, empty (transparent) drawing layer on top, filling the canvas at
    /// Normal 100 %, selected; the Pencil draws into it. One undo step.
    @MainActor
    static func addBlankLayer(to session: TransferSession) {
        let aspect = session.canvasAspect
        let pixels = aspect >= 1 ? CGSize(width: longEdge, height: (longEdge / aspect).rounded())
                                 : CGSize(width: (longEdge * aspect).rounded(), height: longEdge)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        let image = UIGraphicsImageRenderer(size: pixels, format: format).image { _ in }  // nothing drawn: clear
        let layer = Layer(name: "Drawing \(nextNumber(session))", image: image, canvasAspect: aspect)
        layer.opacity = 1
        layer.blend = .normal
        layer.quad = Flatten.fullCanvas
        session.add(layer)
    }

    /// One more than the highest "Drawing n" there is.
    static func nextNumber(_ session: TransferSession) -> Int {
        let numbers = session.layers.compactMap { layer -> Int? in
            guard layer.name.hasPrefix("Drawing ") else { return nil }
            return Int(layer.name.dropFirst("Drawing ".count))
        }
        return (numbers.max() ?? 0) + 1
    }
}

// MARK: - colors as #RRGGBB

extension Color {
    init(hex: String) {
        let digits = hex.replacingOccurrences(of: "#", with: "")
        let v = Int(digits, radix: 16) ?? 0x202020
        self.init(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
    }

    /// #RRGGBB in sRGB, alpha dropped.
    var hex: String {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        UIColor(self).getRed(&r, green: &g, blue: &b, alpha: &a)
        func byte(_ c: CGFloat) -> Int { Int((min(max(c, 0), 1) * 255).rounded()) }
        return String(format: "#%02X%02X%02X", byte(r), byte(g), byte(b))
    }
}

// MARK: - the bar

/// The Pencil's panel at the left: Pencil or Eraser (the Pencil to start
/// with), then the chosen one's size (in the drawing layer's pixels) and
/// opacity, and for the Pencil its color, whose pop-up has a color wheel and
/// the colors chosen last. No Done: it draws until it's turned off.
struct PencilPanel: View {
    @Binding var erasing: Bool
    @Binding var size: Double  // the Pencil's or the Eraser's, whichever is chosen
    @Binding var opacity: Double
    @Binding var colorHex: String
    let pencil: PencilController

    @State private var choosingColor = false

    var body: some View {
        VStack(spacing: 14) {
            VStack(spacing: 6) {
                modeButton("pencil", "Pencil", on: !erasing) { erasing = false }
                modeButton("eraser", "Eraser", on: erasing) { erasing = true }
            }
            column("Size") {
                VerticalSlider(value: Binding(get: { size }, set: { size = $0.rounded() }), range: Pencil.sizes,
                               label: "\(Int(size.rounded()))", height: 170)
                    .accessibilityLabel("Size, pixels")
            }
            column("Opacity") {
                VerticalSlider(value: Binding(get: { (opacity * 100).rounded() }, set: { opacity = $0 / 100 }),
                               range: 5...100, label: "\(Int((opacity * 100).rounded()))", height: 170)
                    .accessibilityLabel("Opacity, percent")
            }
            if !erasing {  // the Eraser has no color
                Button { choosingColor = true } label: {
                    Circle()
                        .fill(Color(hex: colorHex).opacity(opacity))
                        .frame(width: 36, height: 36)
                        .background(Checkerboard().clipShape(Circle()))
                        .overlay(Circle().stroke(Color.white, lineWidth: 2))
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Color")
                .popover(isPresented: $choosingColor, arrowEdge: .leading) { colorPopup }
            }
        }
        .padding(.vertical, 14)
        .frame(width: 64)
        .themedBar()
    }

    /// Pencil or Eraser: a sky-blue tile when chosen.
    private func modeButton(_ symbol: String, _ label: String, on: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(on ? Theme.onAccent : Color.white)
                .frame(width: 44, height: 44)
                .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                    .fill(on ? Theme.accent : Color.clear))
        }
        .accessibilityLabel(label)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func column<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(spacing: 6) {
            Text(title).font(.caption2).foregroundStyle(.secondary)
            content()
        }
    }

    /// One pop-up: the color wheel, and the history of colors chosen.
    private var colorPopup: some View {
        VStack(alignment: .leading, spacing: 16) {
            ColorWheel(hex: $colorHex) { pencil.remember($0) }
            HStack {
                Text("History").font(.headline).foregroundStyle(.secondary)
                Spacer()
                Button("Clear") { pencil.clearRecents() }
                    .buttonStyle(.bordered)
                    .disabled(pencil.recents.isEmpty)
            }
            HStack(spacing: 0) {
                ForEach(0..<PencilController.recentsCount, id: \.self) { i in
                    if i < pencil.recents.count {
                        let hex = pencil.recents[i]
                        Button { colorHex = hex } label: {
                            Rectangle().fill(Color(hex: hex))
                                .overlay(Rectangle().strokeBorder(Theme.accent, lineWidth: hex == colorHex ? 3 : 0))
                        }
                        .accessibilityLabel("Color \(hex)")
                    } else {
                        Rectangle().fill(Color.white.opacity(0.06))
                    }
                }
            }
            .frame(height: 36)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .padding(20)
        .frame(width: 320)
        .themed()
    }
}

/// A color wheel: hue round the ring, and in the disc saturation from left
/// (gray) to right (full) and brightness from top (light) to bottom (black).
/// `onPicked` follows each drag, with the color chosen.
struct ColorWheel: View {
    @Binding var hex: String
    var onPicked: (String) -> Void

    @State private var hue = 0.0
    @State private var saturation = 0.0
    @State private var brightness = 0.0
    @State private var dragging: Part? = nil

    private enum Part { case ring, disc }
    private let size: CGFloat = 280
    private let ringWidth: CGFloat = 36
    private let gap: CGFloat = 12
    private var discDiameter: CGFloat { size - 2 * (ringWidth + gap) }

    var body: some View {
        let c = size / 2
        let ringRadius = c - ringWidth / 2
        let hueAngle = hue * 2 * .pi  // counterclockwise from the right, as in the wheel
        ZStack {
            // The ring: red at the right, then yellow, green, cyan, blue, magenta going counterclockwise.
            Circle()
                .strokeBorder(AngularGradient(colors: stride(from: 1.0, through: 0, by: -1 / 12).map {
                    Color(hue: $0, saturation: 1, brightness: 1)
                }, center: .center), lineWidth: ringWidth)
            ZStack {
                LinearGradient(colors: [.white, Color(hue: hue, saturation: 1, brightness: 1)], startPoint: .leading, endPoint: .trailing)
                LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom)
            }
            .frame(width: discDiameter, height: discDiameter)
            .clipShape(Circle())
            // Where the hue is on the ring, filled with it.
            Circle()
                .fill(Color(hue: hue, saturation: 1, brightness: 1))
                .frame(width: ringWidth + 14, height: ringWidth + 14)
                .overlay(Circle().stroke(Color.white, lineWidth: 2))
                .shadow(radius: 3)
                .position(x: c + ringRadius * cos(hueAngle), y: c - ringRadius * sin(hueAngle))
            // Where the color is in the disc.
            let left = c - discDiameter / 2, top = c - discDiameter / 2
            Circle()
                .stroke(Color.white, lineWidth: 2)
                .frame(width: 24, height: 24)
                .shadow(radius: 2)
                .position(x: left + saturation * discDiameter, y: top + (1 - brightness) * discDiameter)
        }
        .frame(width: size, height: size)
        .contentShape(Circle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { drag in
                    let dx = drag.location.x - c, dy = drag.location.y - c
                    if dragging == nil {
                        let start = hypot(drag.startLocation.x - c, drag.startLocation.y - c)
                        dragging = start > discDiameter / 2 + gap / 2 ? .ring : .disc
                    }
                    if dragging == .ring {
                        let angle = atan2(-dy, dx)  // counterclockwise from the right
                        hue = (angle < 0 ? angle + 2 * .pi : angle) / (2 * .pi)
                    } else {
                        // Kept inside the disc, then read as a square.
                        let r = hypot(dx, dy), limit = discDiameter / 2
                        let k = r > limit ? limit / r : 1
                        saturation = min(max((dx * k + limit) / discDiameter, 0), 1)
                        brightness = min(max(1 - (dy * k + limit) / discDiameter, 0), 1)
                    }
                    hex = Color(hue: hue, saturation: saturation, brightness: brightness).hex
                }
                .onEnded { _ in
                    dragging = nil
                    onPicked(hex)
                }
        )
        .onAppear(perform: read)
        .onChange(of: hex) { if dragging == nil { read() } }  // chosen from the history
        .accessibilityLabel("Color wheel")
    }

    /// Hue, saturation and brightness from `hex`; the hue is kept for grays.
    private func read() {
        var h: CGFloat = 0, s: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        UIColor(Color(hex: hex)).getHue(&h, saturation: &s, brightness: &b, alpha: &a)
        if s > 0.001 { hue = Double(h) }
        saturation = Double(s)
        brightness = Double(b)
    }
}

/// Light and dark gray squares, behind what may be see-through.
struct Checkerboard: View {
    var square: CGFloat = 6

    var body: some View {
        Canvas { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Color(white: 0.85)))
            let columns = Int(ceil(size.width / square)), rows = Int(ceil(size.height / square))
            var dark = Path()
            for row in 0..<rows {
                for column in 0..<columns where (row + column) % 2 == 1 {
                    dark.addRect(CGRect(x: CGFloat(column) * square, y: CGFloat(row) * square, width: square, height: square))
                }
            }
            context.fill(dark, with: .color(Color(white: 0.65)))
        }
        .accessibilityHidden(true)
    }
}
