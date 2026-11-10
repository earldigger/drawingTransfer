import SwiftUI
import UIKit

/// A color picked from a layer (Swatch in canvastransfer/models.py). (u, v)
/// is where, in fractions of the layer's image, so its marker follows the
/// layer through every transform. Numbered by its place in the list.
struct Swatch: Codable, Equatable, Identifiable {
    var id = UUID()
    var layerID: UUID
    var u: Double
    var v: Double
    var red: Int
    var green: Int
    var blue: Int
    var radius: Int? = nil  // the sample size it was picked with, for reading it again; nil = 1 pixel

    var color: Color { Color(red: Double(red) / 255, green: Double(green) / 255, blue: Double(blue) / 255) }
    var hex: String { String(format: "#%02X%02X%02X", red, green, blue) }

    /// CIELAB lightness, 0 (black) to 100 (white): the swatch's value.
    var value: Double {
        func linear(_ c: Int) -> Double {
            let s = Double(c) / 255
            return s <= 0.04045 ? s / 12.92 : pow((s + 0.055) / 1.055, 2.4)
        }
        let y = 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
        return y > 216.0 / 24389 ? 116 * cbrt(y) - 16 : y * 24389 / 27
    }

    /// Black or white, whichever reads on top of the swatch.
    var labelColor: Color { value > 60 ? .black : .white }
}

/// How big an area Pick averages, in the layer image's pixels (the prototype's sample size).
enum SampleSize: Int, CaseIterable, Identifiable {
    case point = 0
    case small = 2  // 5 × 5
    case large = 5  // 11 × 11

    var id: Int { rawValue }
    var label: String {
        switch self {
        case .point: "1 px"
        case .small: "5 px"  // a 5 × 5 square
        case .large: "11 px"  // 11 × 11
        }
    }
}

/// A layer image's pixels, read once, for picking.
final class PixelBuffer {
    let width: Int
    let height: Int
    private var bytes: [UInt8]  // RGBA, sRGB, 8 bits each

    init?(_ image: UIImage) {
        guard let cg = image.cgImage else { return nil }
        width = cg.width
        height = cg.height
        bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drawn: Bool = bytes.withUnsafeMutableBytes { raw in
            guard let context = CGContext(data: raw.baseAddress, width: width, height: height, bitsPerComponent: 8,
                                          bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drawn else { return nil }
    }

    /// The mean color of the square `radius` pixels around (u, v) in fractions
    /// of the image, weighted by alpha (sample_average in color_study.py).
    func average(u: Double, v: Double, radius: Int) -> (Int, Int, Int)? {
        let cx = Int((u * Double(width)).rounded(.down)), cy = Int((v * Double(height)).rounded(.down))
        guard (0..<width).contains(cx), (0..<height).contains(cy) else { return nil }
        var r = 0.0, g = 0.0, b = 0.0, total = 0.0
        for y in max(0, cy - radius)...min(height - 1, cy + radius) {
            for x in max(0, cx - radius)...min(width - 1, cx + radius) {
                let i = (y * width + x) * 4
                let a = Double(bytes[i + 3]) / 255
                guard a > 0 else { continue }
                // Premultiplied: un-premultiply, then weight by alpha.
                r += Double(bytes[i]); g += Double(bytes[i + 1]); b += Double(bytes[i + 2])
                total += a
            }
        }
        guard total > 0 else { return nil }
        return (Int((r / total).rounded()), Int((g / total).rounded()), Int((b / total).rounded()))
    }

    /// A `size` × `size` block of pixels around (u, v), for the loupe.
    func patch(u: Double, v: Double, size: Int) -> UIImage? {
        let cx = Int(u * Double(width)), cy = Int(v * Double(height)), half = size / 2
        var out = [UInt8](repeating: 0, count: size * size * 4)
        for y in 0..<size {
            for x in 0..<size {
                let sx = cx - half + x, sy = cy - half + y
                guard (0..<width).contains(sx), (0..<height).contains(sy) else { continue }
                let i = (sy * width + sx) * 4, o = (y * size + x) * 4
                out[o] = bytes[i]; out[o + 1] = bytes[i + 1]; out[o + 2] = bytes[i + 2]; out[o + 3] = bytes[i + 3]
            }
        }
        let data = Data(out) as CFData
        guard let provider = CGDataProvider(data: data),
              let cg = CGImage(width: size, height: size, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: size * 4,
                               space: CGColorSpace(name: CGColorSpace.sRGB)!,
                               bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                               provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)
        else { return nil }
        return UIImage(cgImage: cg)
    }
}

/// What's under the finger while picking: where, and the color there.
struct PickProbe: Equatable {
    var location: CGPoint  // in canvas points
    var layerID: UUID
    var u: Double
    var v: Double
    var rgb: (Int, Int, Int)?  // nil = outside the layer, or cropped off
    var patch: UIImage?

    static func == (a: PickProbe, b: PickProbe) -> Bool {
        a.location == b.location && a.u == b.u && a.v == b.v && a.rgb?.0 == b.rgb?.0 && a.rgb?.1 == b.rgb?.1 && a.rgb?.2 == b.rgb?.2
    }

    /// Reads the selected layer at a canvas point, through its corners: what
    /// the canvas shows of it, so `shown` when it's simplified.
    static func at(_ location: CGPoint, layer: Layer, canvas: CGSize, sample: SampleSize,
                   shown: PixelBuffer? = nil) -> PickProbe? {
        guard let f = QuadGeometry.imageFraction(of: location, in: layer.quadPoints(in: canvas)) else { return nil }
        let inside = (0...1).contains(f.x) && (0...1).contains(f.y)
            && layer.crop.contains(CGPoint(x: min(f.x, 0.999_999), y: min(f.y, 0.999_999)))
        let pixels = shown ?? layer.pixels()
        return PickProbe(location: location, layerID: layer.id, u: f.x, v: f.y,
                         rgb: inside ? pixels?.average(u: f.x, v: f.y, radius: sample.rawValue) : nil,
                         patch: pixels?.patch(u: f.x, v: f.y, size: 15))
    }
}

/// The loupe above the finger: the layer's pixels, magnified, with the
/// sample area marked, and the averaged color with its hex code.
struct Loupe: View {
    let probe: PickProbe
    let sample: SampleSize

    var body: some View {
        let size: CGFloat = 120, cell = size / 15
        VStack(spacing: 0) {
            ZStack {
                if let patch = probe.patch {
                    Image(uiImage: patch).interpolation(.none).resizable().frame(width: size, height: size)
                } else {
                    Color.black.frame(width: size, height: size)
                }
                Rectangle()
                    .stroke(Color.white, lineWidth: 1.5)
                    .shadow(color: .black, radius: 1)
                    .frame(width: cell * CGFloat(sample.rawValue * 2 + 1), height: cell * CGFloat(sample.rawValue * 2 + 1))
            }
            .frame(width: size, height: size)
            HStack {
                if let rgb = probe.rgb {
                    Text(String(format: "#%02X%02X%02X", rgb.0, rgb.1, rgb.2)).font(.caption.monospaced())
                } else {
                    Text("Not on this layer").font(.caption)
                }
            }
            .frame(width: size, height: 30)
            .background(probe.rgb.map { Color(red: Double($0.0) / 255, green: Double($0.1) / 255, blue: Double($0.2) / 255) } ?? Color(white: 0.15))
            .foregroundStyle(probe.rgb.map { Swatch(layerID: probe.layerID, u: 0, v: 0, red: $0.0, green: $0.1, blue: $0.2).labelColor } ?? .white)
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.white, lineWidth: 3))
        .shadow(radius: 8)
        .allowsHitTesting(false)
    }
}

/// Numbered markers where each swatch was picked, following its layer.
struct SwatchMarkers: View {
    let swatches: [Swatch]
    let layers: [Layer]
    let canvas: CGSize
    let selectedID: UUID?
    let scale: CGFloat  // the view's zoom, so markers keep their size on screen

    var body: some View {
        ZStack(alignment: .topLeading) {
            ForEach(Array(swatches.enumerated()), id: \.element.id) { index, swatch in
                if let layer = layers.first(where: { $0.id == swatch.layerID }), layer.isVisible {
                    let point = QuadGeometry.point(swatch.u, swatch.v, in: layer.quadPoints(in: canvas))
                    let selected = swatch.id == selectedID
                    Text("\(index + 1)")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(swatch.labelColor)
                        .frame(width: 22, height: 22)
                        .background(Circle().fill(swatch.color))
                        .overlay(Circle().stroke(selected ? Theme.accent : Color.white, lineWidth: selected ? 3 : 2))
                        .shadow(color: .black.opacity(0.5), radius: 2)
                        .scaleEffect(1 / scale)
                        .position(point)
                }
            }
        }
        .frame(width: canvas.width, height: canvas.height, alignment: .topLeading)
        .allowsHitTesting(false)
    }
}

/// The color tool's bottom bar (the eyedropper in the top bar). Left: the
/// Eyedropper (touch the canvas to add swatches), Simplify and Highlight,
/// each on until tapped again, with its options in a pop-up above it. Then
/// the swatches as numbered chips; right: hide or show the swatch markers,
/// delete all (asks first), and Done.
struct ColorBar: View {
    @Bindable var session: TransferSession
    @Binding var selectedID: UUID?
    @Binding var picking: Bool
    @Binding var view: ColorView
    @Binding var sample: SampleSize
    @Binding var simplify: SimplifySettings
    @Binding var highlight: HighlightSettings
    @Binding var markersShown: Bool
    let working: Bool
    var onDone: () -> Void

    enum Tool { case pick, simplify, highlight }

    @State private var popup: Tool? = nil  // the options shown: the tool last turned on
    @State private var confirmingDelete = false

    // The layout, as in the design: tiles 44 pt, 11 apart, 10 in from the bar's edge.
    private static let tile: CGFloat = 44, tileSpacing: CGFloat = 11, inset: CGFloat = 10
    private static let arrowInset: CGFloat = 38  // a pop-up's arrow, from its leading edge
    private static let doneWidth: CGFloat = 78, trailingSpacing: CGFloat = 14
    private static let barHeight: CGFloat = 64

    var body: some View {
        HStack(spacing: 0) {
            HStack(spacing: Self.tileSpacing) {
                toolTile("eyedropper", "Eyedropper", tool: .pick, on: picking)
                toolTile("circle.lefthalf.filled", "Simplify", tool: .simplify, on: view == .simplify)
                toolTile("pencil.line", "Highlight", tool: .highlight, on: view == .highlight)
            }
            .padding(.leading, Self.inset)
            .padding(.trailing, 9)
            Divider()
            chips
            if working { ProgressView().controlSize(.small).padding(.horizontal, 8) }
            Divider()
            HStack(spacing: Self.trailingSpacing) {
                SwatchMarkersToggle(isOn: $markersShown)
                Button {
                    withAnimation(.snappy) { confirmingDelete.toggle() }
                } label: {
                    Image(systemName: "trash").font(.system(size: 20)).frame(width: 44, height: 44)
                }
                .accessibilityLabel("Delete all swatches")
                .disabled(session.swatches.isEmpty)
                DoneButton(action: onDone)
            }
            .padding(.leading, 17)
            .padding(.trailing, Self.trailingSpacing)
        }
        .frame(maxWidth: .infinity)  // the whole width of the screen
        .frame(height: Self.barHeight)
        .themedBar()
        .overlay(alignment: .bottomLeading) { toolPopup }
        .overlay(alignment: .bottomTrailing) { deletePopup }
        .onChange(of: session.swatches.isEmpty) { _, empty in if empty { confirmingDelete = false } }
    }

    // MARK: tools

    private func toolTile(_ symbol: String, _ label: String, tool: Tool, on: Bool) -> some View {
        Button { toggle(tool) } label: {
            Image(systemName: symbol)
                .font(.system(size: 22))
                .foregroundStyle(.white)
                .frame(width: Self.tile, height: Self.tile)
                .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                    .fill(on ? Theme.lavender : Color.clear))
        }
        .accessibilityLabel(label)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// On, with its options showing; or off. Simplify and Highlight take turns.
    /// The Eyedropper turns on and off. Simplify and Highlight turn on with
    /// their options showing; tapped again they only hide or show the options,
    /// and stay on until the other one, Off or Done.
    private func toggle(_ tool: Tool) {
        let nowOn: Bool
        switch tool {
        case .pick:
            picking.toggle()
            nowOn = picking
        case .simplify, .highlight:
            let mode: ColorView = tool == .simplify ? .simplify : .highlight
            if view == mode {
                withAnimation(.snappy) { popup = popup == tool ? nil : tool }
                return
            }
            view = mode
            nowOn = true
        }
        withAnimation(.snappy) {
            if nowOn {
                popup = tool
            } else if popup == tool {
                popup = nil
            }
            if popup == .simplify && view != .simplify || popup == .highlight && view != .highlight { popup = nil }
        }
    }

    @ViewBuilder
    private var toolPopup: some View {
        if let popup {
            let index: CGFloat = switch popup { case .pick: 0; case .simplify: 1; case .highlight: 2 }
            let center = Self.inset + Self.tile / 2 + index * (Self.tile + Self.tileSpacing)
            Callout(arrowInset: Self.arrowInset) {
                switch popup {
                case .pick: pickOptions
                case .simplify: simplifyOptions
                case .highlight: highlightOptions
                }
            }
            .fixedSize()  // its own size, not the bar's
            .offset(x: center - Self.arrowInset, y: -(Self.barHeight + 4))  // just above the bar
            .transition(.opacity)
        }
    }

    private var pickOptions: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Add a Swatch", systemImage: "eyedropper").font(.title3)
            Picker("Sample size", selection: $sample) {
                ForEach(SampleSize.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)
        }
    }

    private var simplifyOptions: some View {
        VStack(alignment: .leading, spacing: 16) {
            popupHeader("Simplify", symbol: "circle.lefthalf.filled")
            HStack(alignment: .top, spacing: 36) {
                sliderColumn("Steps") {
                    VerticalSlider(value: Binding(get: { Double(simplify.count) }, set: { simplify.count = Int($0) }),
                                   range: 1...24, label: "\(simplify.count)")
                }
                sliderColumn("Smoothing") {
                    VerticalSlider(value: Binding(get: { Double(simplify.smoothing) }, set: { simplify.smoothing = Int($0) }),
                                   range: 0...6)
                }
            }
            .frame(maxWidth: .infinity)
            Picker("Show", selection: $simplify.mode) {
                Text("Colors").tag(ColorStudy.SimplifyMode.colors)
                Text("Values").tag(ColorStudy.SimplifyMode.values)
            }
            .pickerStyle(.segmented)
            .frame(width: 220)
        }
    }

    private var highlightOptions: some View {
        VStack(alignment: .leading, spacing: 16) {
            popupHeader("Highlight", symbol: "pencil.line")
            if session.swatches.isEmpty {
                Text("Add a swatch first.").font(.callout).foregroundStyle(.secondary)
            }
            // Range: how far from a swatch's color still counts as its color.
            sliderColumn("Range") {
                VerticalSlider(value: $highlight.tolerance, range: 2...40, label: "\(Int(highlight.tolerance.rounded()))")
            }
            .frame(maxWidth: .infinity)
            Picker("Show", selection: $highlight.selectedOnly) {
                Text("All").tag(false)
                Text("Selected").tag(true)
            }
            .pickerStyle(.segmented)
            .frame(width: 220)
        }
    }

    /// Simplify's or Highlight's title, with Off (ends the mode) and ⌄ (hides
    /// the options; the mode stays on).
    private func popupHeader(_ title: String, symbol: String) -> some View {
        HStack(spacing: 14) {
            Label(title, systemImage: symbol).font(.title3.weight(.semibold))
            Spacer(minLength: 12)
            Button("Off") {
                withAnimation(.snappy) {
                    view = .normal
                    popup = nil
                }
            }
            Button {
                withAnimation(.snappy) { popup = nil }
            } label: {
                Image(systemName: "chevron.down").font(.body.weight(.semibold)).frame(width: 32, height: 32)
            }
            .accessibilityLabel("Hide \(title.lowercased()) options")
        }
    }

    private func sliderColumn<Slider: View>(_ title: String, @ViewBuilder slider: () -> Slider) -> some View {
        VStack(spacing: 10) {
            Text(title).foregroundStyle(.secondary)
            slider()
        }
    }

    // MARK: delete all

    @ViewBuilder
    private var deletePopup: some View {
        if confirmingDelete {
            let arrowInset: CGFloat = 54
            // The trash's middle, in from the bar's trailing edge.
            let trash = Self.trailingSpacing + Self.doneWidth + Self.trailingSpacing + 22
            Callout(arrowInset: arrowInset, trailing: true) {
                HStack(spacing: 14) {
                    Button("Cancel") { withAnimation(.snappy) { confirmingDelete = false } }
                        .foregroundStyle(.secondary)
                    Button("Delete All Swatches") {
                        session.swatches.removeAll()  // one undo step
                        selectedID = nil
                        confirmingDelete = false
                    }
                    .buttonStyle(.accent)
                }
            }
            .fixedSize()
            .offset(x: -(trash - arrowInset), y: -(Self.barHeight + 4))
            .transition(.opacity)
        }
    }

    // MARK: chips

    @ViewBuilder
    private var chips: some View {
        if session.swatches.isEmpty {
            Text(picking ? "Touch the canvas to add a swatch from the selected layer."
                         : "Tap the eyedropper, then touch the canvas to add a swatch.")
                .font(.callout).foregroundStyle(.secondary)
                .padding(.horizontal, 14)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(Array(session.swatches.enumerated()), id: \.element.id) { index, swatch in
                        chip(swatch, number: index + 1)
                    }
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
            }
            .frame(maxWidth: .infinity)  // the chips take the room the bar has
        }
    }

    private func chip(_ swatch: Swatch, number: Int) -> some View {
        let selected = swatch.id == selectedID
        // In Highlight, each chip's edge is its highlight color.
        let edge = view == .highlight ? ColorStudy.highlightColor(number - 1) : Color.white.opacity(0.4)
        return Button {
            selectedID = selected ? nil : swatch.id
        } label: {
            Text("\(number)")
                .font(.caption.weight(.bold))
                .foregroundStyle(swatch.labelColor)
                .frame(width: 44, height: 44)
                .background(RoundedRectangle(cornerRadius: 8).fill(swatch.color))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(selected ? Theme.accent : edge,
                                                                  lineWidth: selected || view == .highlight ? 3 : 1))
        }
        .contextMenu {
            Button("Delete swatch \(number)", systemImage: "trash", role: .destructive) {
                session.swatches.removeAll { $0.id == swatch.id }
                if selectedID == swatch.id { selectedID = nil }
            }
        }
        .accessibilityLabel("Swatch \(number), \(swatch.hex)")
    }
}
