import CoreImage
import SwiftUI
import UIKit

/// A layer's adjustments, as in the prototype (`Adjustments` in
/// canvastransfer/models.py), applied in this order: invert, levels,
/// hue / saturation (or colorize), lightness. Values use the prototype's
/// ranges: levels in 0...255, hue in degrees, the rest in -100...100.
struct Adjustments: Codable, Equatable {
    var invert = false
    var black: Double = 0  // levels dark point
    var gamma: Double = 1  // levels midtones; > 1 lightens, < 1 darkens
    var white: Double = 255  // levels light point
    var hue: Double = 0  // -180...180, around the color wheel
    var saturation: Double = 0  // -100 (gray) ... 100
    var lightness: Double = 0  // -100 (black) ... 100 (white)
    var colorize = false  // tint the whole layer one color instead
    var colorizeHue: Double = 0  // 0...360
    var colorizeSaturation: Double = 25  // 0...100, tint strength

    var isIdentity: Bool { self == Adjustments() }
    var levelsIsIdentity: Bool { !invert && black == 0 && white == 255 && gamma == 1 }
}

/// Applies `Adjustments` with Core Image, on the GPU.
enum Look {
    private static let context = CIContext()

    /// The adjusted image, or nil to show the original.
    static func adjusted(_ image: UIImage, _ a: Adjustments) -> UIImage? {
        guard !a.isIdentity, var ci = CIImage(image: image) else { return nil }
        if !a.levelsIsIdentity {
            ci = curve(ci) { x in
                let v = a.invert ? 1 - x : x
                let t = min(max((v * 255 - a.black) / max(a.white - a.black, 1), 0), 1)
                return pow(t, 1 / max(a.gamma, 0.001))
            }
        }
        if a.colorize {
            // Keep each pixel's brightness, give it one tint.
            let tint = UIColor(hue: CGFloat(a.colorizeHue.truncatingRemainder(dividingBy: 360) / 360),
                               saturation: CGFloat(min(max(a.colorizeSaturation, 0), 100) / 100),
                               brightness: 1, alpha: 1)
            ci = ci.applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 0])
                .applyingFilter("CIColorMonochrome", parameters: [kCIInputColorKey: CIColor(color: tint),
                                                                   kCIInputIntensityKey: 1])
        } else {
            if a.hue != 0 {
                ci = ci.applyingFilter("CIHueAdjust", parameters: [kCIInputAngleKey: a.hue * .pi / 180])
            }
            if a.saturation != 0 {
                ci = ci.applyingFilter("CIColorControls",
                                       parameters: [kCIInputSaturationKey: 1 + min(max(a.saturation, -100), 100) / 100])
            }
        }
        if a.lightness != 0 {
            // Photoshop's Lightness: toward white (+) or black (-).
            let v = min(max(a.lightness, -100), 100) / 100
            ci = curve(ci) { x in v >= 0 ? x + (1 - x) * v : x * (1 + v) }
        }
        guard let cg = context.createCGImage(ci, from: ci.extent) else { return nil }
        return UIImage(cgImage: cg, scale: image.scale, orientation: .up)
    }

    /// The same 0...1 curve on red, green and blue, in sRGB like the
    /// prototype's 8-bit lookup tables.
    private static func curve(_ image: CIImage, _ f: (Double) -> Double) -> CIImage {
        var table: [Float] = []
        for i in 0..<256 {
            let y = Float(f(Double(i) / 255))
            table += [y, y, y]
        }
        let data = table.withUnsafeBufferPointer { Data(buffer: $0) }
        return image.applyingFilter("CIColorCurves", parameters: [
            "inputCurvesData": data,
            "inputCurvesDomain": CIVector(x: 0, y: 1),
            "inputColorSpace": CGColorSpace(name: CGColorSpace.sRGB) as Any,  // the key constant is iOS 26+
        ])
    }
}

/// The Adjust popover: invert, levels, hue / saturation / lightness,
/// colorize, reset. Live on the canvas; each slider drag is one undo step.
/// The phone's Adjust: a strip that comes up out of the top of the layer
/// bar. A row of adjustments, each an icon with its name, scrolls sideways;
/// the chosen one shows its value, and the thin slider along the top sets it.
/// Invert and Colorize are switches: tapping them turns them on or off.
struct AdjustStrip: View {
    @Bindable var layer: Layer
    @Environment(History.self) private var history
    @State private var selected = Item.black

    enum Item: String, CaseIterable, Identifiable {
        case invert, black, mid, white, hue, saturation, lightness, colorize
        var id: String { rawValue }

        var title: String {
            switch self {
            case .invert: "invert"
            case .black: "black"
            case .mid: "mid"
            case .white: "white"
            case .hue: "hue"
            case .saturation: "saturation"
            case .lightness: "lightness"
            case .colorize: "colorize"
            }
        }

        var symbol: String {
            switch self {
            case .invert: "circle.righthalf.filled"
            case .black: "circle.fill"
            case .mid: "circle.bottomhalf.filled"
            case .white: "circle"
            case .hue: "paintpalette"
            case .saturation: "drop.halffull"
            case .lightness: "sun.max"
            case .colorize: "paintbrush"
            }
        }

        var isSwitch: Bool { self == .invert || self == .colorize }
    }

    var body: some View {
        VStack(spacing: 0) {
            if let value = value(selected) {
                ThinSlider(value: value, range: range(selected)) { editing in
                    if editing { history.hold("look") } else { history.release("look") }  // one drag, one step
                }
                .accessibilityLabel(selected.title)
                .accessibilityValue(text(selected) ?? "")
                .padding(.horizontal, 14)
                .padding(.top, 6)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(Item.allCases) { tile($0) }
                    Button { layer.adjustments = Adjustments() } label: {
                        VStack(spacing: 4) {
                            Image(systemName: "arrow.counterclockwise").font(.system(size: 20)).frame(width: 44, height: 44)
                            Text("reset").font(.caption2.weight(.semibold))
                        }
                        .frame(minWidth: 52)
                    }
                    .buttonStyle(.plain)
                    .disabled(layer.adjustments.isIdentity)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
        }
        .background(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18, style: .continuous).fill(Theme.popup))
        .onChange(of: layer.adjustments.black) { keepLevelsInOrder(movedBlack: true) }
        .onChange(of: layer.adjustments.white) { keepLevelsInOrder(movedBlack: false) }
    }

    /// An adjustment: its icon (filled sky blue with the value when chosen,
    /// or when a switch is on) and its name.
    private func tile(_ item: Item) -> some View {
        let on = item.isSwitch ? isOn(item) : item == selected
        return Button {
            if item == .invert { layer.adjustments.invert.toggle() }
            else if item == .colorize { layer.adjustments.colorize.toggle() }
            else { selected = item }
        } label: {
            VStack(spacing: 4) {
                ZStack {
                    RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                        .fill(on ? Theme.accent : Color.white.opacity(0.08))
                    if item == selected, let text = text(item) {
                        Text(text).font(.caption.weight(.bold)).monospacedDigit()
                            .minimumScaleFactor(0.6).lineLimit(1).padding(.horizontal, 3)
                            .foregroundStyle(Theme.onAccent)
                    } else {
                        Image(systemName: item.symbol).font(.system(size: 20))
                            .foregroundStyle(on ? Theme.onAccent : Color.white)
                    }
                }
                .frame(width: 44, height: 44)
                .overlay(alignment: .topTrailing) {  // changed from the start
                    if changed(item) && !on { Circle().fill(Theme.accent).frame(width: 7, height: 7).offset(x: 2, y: -2) }
                }
                Text(item.title).font(.caption2.weight(.semibold)).lineLimit(1)
            }
            .frame(minWidth: 52)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(item.title)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func isOn(_ item: Item) -> Bool {
        item == .invert ? layer.adjustments.invert : item == .colorize ? layer.adjustments.colorize : false
    }

    private func changed(_ item: Item) -> Bool {
        let a = layer.adjustments, none = Adjustments()
        switch item {
        case .invert: return a.invert
        case .black: return a.black != none.black
        case .mid: return a.gamma != none.gamma
        case .white: return a.white != none.white
        case .hue: return a.colorize ? a.colorizeHue != none.colorizeHue : a.hue != none.hue
        case .saturation: return a.colorize ? a.colorizeSaturation != none.colorizeSaturation : a.saturation != none.saturation
        case .lightness: return a.lightness != none.lightness
        case .colorize: return a.colorize
        }
    }

    /// What the slider sets. With Colorize on, Hue and Saturation set the tint.
    private func value(_ item: Item) -> Binding<Double>? {
        let colorize = layer.adjustments.colorize
        switch item {
        case .black: return $layer.adjustments.black
        case .mid: return $layer.adjustments.gamma
        case .white: return $layer.adjustments.white
        case .hue: return colorize ? $layer.adjustments.colorizeHue : $layer.adjustments.hue
        case .saturation: return colorize ? $layer.adjustments.colorizeSaturation : $layer.adjustments.saturation
        case .lightness: return $layer.adjustments.lightness
        case .invert, .colorize: return nil
        }
    }

    private func range(_ item: Item) -> ClosedRange<Double> {
        let colorize = layer.adjustments.colorize
        switch item {
        case .black: return 0...254
        case .mid: return 0.2...5
        case .white: return 1...255
        case .hue: return colorize ? 0...360 : -180...180
        case .saturation: return colorize ? 0...100 : -100...100
        case .lightness: return -100...100
        case .invert, .colorize: return 0...1
        }
    }

    private func text(_ item: Item) -> String? {
        guard let v = value(item)?.wrappedValue else { return nil }
        let colorize = layer.adjustments.colorize
        switch item {
        case .mid: return String(format: "%.2f", v)
        case .hue: return String(format: colorize ? "%.0f°" : "%+.0f°", v)
        case .saturation where !colorize, .lightness: return String(format: "%+.0f", v)
        default: return String(format: "%.0f", v)
        }
    }

    /// The black point stays below the white point.
    private func keepLevelsInOrder(movedBlack: Bool) {
        let a = layer.adjustments
        guard a.black >= a.white else { return }
        if movedBlack { layer.adjustments.black = a.white - 1 } else { layer.adjustments.white = a.black + 1 }
    }
}

/// A thin bar slider without a knob: drag along it (or tap) to set the value.
struct ThinSlider: View {
    @Binding var value: Double
    let range: ClosedRange<Double>
    var onEditing: (Bool) -> Void = { _ in }

    @State private var dragging = false

    var body: some View {
        GeometryReader { g in
            let span = range.upperBound - range.lowerBound
            let fraction = min(max((value - range.lowerBound) / span, 0), 1)
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.22))
                Capsule().fill(Theme.accent).frame(width: max(g.size.width * fraction, 10))
            }
            .frame(height: 12)
            .frame(maxHeight: .infinity)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { drag in
                        if !dragging { dragging = true; onEditing(true) }
                        let f = min(max(drag.location.x / max(g.size.width, 1), 0), 1)
                        value = range.lowerBound + f * span
                    }
                    .onEnded { _ in
                        dragging = false
                        onEditing(false)
                    }
            )
        }
        .frame(height: 30)
        .accessibilityElement()
        .accessibilityAdjustableAction { direction in
            let step = (range.upperBound - range.lowerBound) / 50
            switch direction {
            case .increment: value = min(value + step, range.upperBound)
            case .decrement: value = max(value - step, range.lowerBound)
            @unknown default: break
            }
        }
    }
}

struct LookPanel: View {
    @Bindable var layer: Layer
    @Environment(History.self) private var history

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Toggle("Invert", isOn: $layer.adjustments.invert)

                section("Levels")
                slider("Black point", $layer.adjustments.black, 0...254, "%.0f")
                slider("Midtones", $layer.adjustments.gamma, 0.2...5, "%.2f")
                slider("White point", $layer.adjustments.white, 1...255, "%.0f")

                section("Hue / Saturation")
                Toggle("Colorize", isOn: $layer.adjustments.colorize)
                if layer.adjustments.colorize {
                    slider("Hue", $layer.adjustments.colorizeHue, 0...360, "%.0f°")
                    slider("Strength", $layer.adjustments.colorizeSaturation, 0...100, "%.0f")
                } else {
                    slider("Hue", $layer.adjustments.hue, -180...180, "%+.0f°")
                    slider("Saturation", $layer.adjustments.saturation, -100...100, "%+.0f")
                }
                slider("Lightness", $layer.adjustments.lightness, -100...100, "%+.0f")

                Button("Reset adjustments", role: .destructive) { layer.adjustments = Adjustments() }
                    .disabled(layer.adjustments.isIdentity)
                    .padding(.top, 6)
            }
            .padding(20)
        }
        .frame(width: 340)
        .frame(maxHeight: 560)
        .onChange(of: layer.adjustments.black) { keepLevelsInOrder(movedBlack: true) }
        .onChange(of: layer.adjustments.white) { keepLevelsInOrder(movedBlack: false) }
    }

    private func section(_ title: String) -> some View {
        Text(title).font(.headline).padding(.top, 6)
    }

    private func slider(_ title: String, _ value: Binding<Double>, _ range: ClosedRange<Double>,
                        _ format: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
            ValueSlider(value: value, range: range, label: String(format: format, value.wrappedValue)) { editing in
                if editing { history.hold("look") } else { history.release("look") }  // one drag, one step
            }
            .accessibilityLabel(title)
        }
    }

    /// The black point stays below the white point.
    private func keepLevelsInOrder(movedBlack: Bool) {
        let a = layer.adjustments
        guard a.black >= a.white else { return }
        if movedBlack { layer.adjustments.black = a.white - 1 } else { layer.adjustments.white = a.black + 1 }
    }
}
