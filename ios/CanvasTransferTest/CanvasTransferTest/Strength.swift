import SwiftUI
import UIKit

/// A tinting strength measured on the iPad from a photo of your own tint.
struct MeasuredStrength: Codable, Equatable {
    var strength: Double
    var paintParts: Double  // the tint's ratio, e.g. 1 : 3
    var whiteParts: Double
    var whiteName: String
    var hueOff: Double  // ΔE between the model's tint and yours at this strength: how far the hue is off
    var date: Date
}

/// Strength from a tint (CLAUDE.md: paint + white at a known ratio, compared
/// at matching lightness). The white swatch from the same photo cancels the
/// photo's exposure and color cast; then the share of paint at which
/// Mixbox's tint has your tint's lightness says how strong the paint is.
/// A paint of strength k mixed s : (1 − s) with a white of strength w does
/// what an average paint would at e = k·s / (k·s + w·(1 − s)), so
/// k = w · e·(1 − s) / (s·(1 − e)).
enum StrengthMeasure {
    struct Result {
        var strength: Double
        var effective: Double  // the share of paint that Mixbox needs for your lightness
        var tint: (Int, Int, Int)  // your tint, with the photo's cast removed
        var model: (Int, Int, Int)  // Mixbox's tint at that share
        var hueOff: Double  // ΔE between them; lightness matches, so this is hue and chroma
        var clipped: Bool  // the tint is lighter or darker than any mix of the two: strength is a limit
    }

    static let range = 0.05...50.0

    static func measure(paint: Paint, white: Paint, paintParts: Double, whiteParts: Double,
                        tintSwatch: (Int, Int, Int), whiteSwatch: (Int, Int, Int), library: PaintLibrary) -> Result? {
        guard let paintLab = library.color(of: paint), let whiteLab = library.color(of: white),
              paintParts > 0, whiteParts > 0, Mixbox.isAvailable else { return nil }
        // Undo the photo: scale each channel, in linear light, so the photographed white is the white's own color.
        let whiteTrue = PaintColor.srgb(whiteLab).rgb
        func linear(_ c: Int) -> Double {
            let s = Double(c) / 255
            return s <= 0.04045 ? s / 12.92 : pow((s + 0.055) / 1.055, 2.4)
        }
        func encode(_ v: Double) -> Int {
            let c = min(max(v, 0), 1)
            return Int(((c <= 0.0031308 ? 12.92 * c : 1.055 * pow(c, 1 / 2.4) - 0.055) * 255).rounded())
        }
        func fix(_ t: Int, _ shot: Int, _ truth: Int) -> Int { encode(linear(t) * linear(truth) / max(linear(shot), 1e-4)) }
        let tint = (fix(tintSwatch.0, whiteSwatch.0, whiteTrue.0), fix(tintSwatch.1, whiteSwatch.1, whiteTrue.1),
                    fix(tintSwatch.2, whiteSwatch.2, whiteTrue.2))
        let goal = PaintColor.lab(tint).L

        let p = PaintColor.srgb(paintLab).rgb
        let zp = Mixbox.latent(Double(p.0) / 255, Double(p.1) / 255, Double(p.2) / 255)
        let zw = Mixbox.latent(Double(whiteTrue.0) / 255, Double(whiteTrue.1) / 255, Double(whiteTrue.2) / 255)
        func mix(_ e: Double) -> (Double, Double, Double) { Mixbox.rgb(Mixbox.sum([(zp, e), (zw, 1 - e)])) }
        func lightness(_ e: Double) -> Double { let c = mix(e); return PaintColor.lab(c.0, c.1, c.2).L }

        // Lightness runs from the white's (e = 0) to the paint's (e = 1); find where it's yours.
        var lo = 0.0, hi = 1.0
        let darkerWithPaint = lightness(1) < lightness(0)
        let clipped = darkerWithPaint ? (goal > lightness(0) || goal < lightness(1)) : (goal < lightness(0) || goal > lightness(1))
        for _ in 0..<40 {
            let mid = (lo + hi) / 2
            if (lightness(mid) > goal) == darkerWithPaint { lo = mid } else { hi = mid }
        }
        let e = min(max((lo + hi) / 2, 1e-4), 1 - 1e-4)
        let s = paintParts / (paintParts + whiteParts)
        let k = min(max(white.strength * e * (1 - s) / (s * (1 - e)), range.lowerBound), range.upperBound)
        let m = mix(e)
        let model = (Int((m.0 * 255).rounded()), Int((m.1 * 255).rounded()), Int((m.2 * 255).rounded()))
        return Result(strength: k, effective: e, tint: tint, model: model,
                      hueOff: PaintColor.deltaE(PaintColor.lab(tint), PaintColor.lab(model)), clipped: clipped)
    }
}

/// Measure strength: which swatches are the tint and the white, which paint
/// and white they are, and the ratio; then the strength, to use from now on.
/// Below, every strength measured on the iPad, to copy into the prototype.
struct MeasureStrengthView: View {
    let swatches: [Swatch]
    var onDone: () -> Void

    @State private var library = PaintLibrary.shared
    @State private var tintID: UUID? = nil
    @State private var whiteSwatchID: UUID? = nil
    @State private var paintID = ""
    @State private var whitePaintID = ""
    @State private var paintParts = 1.0
    @State private var whiteParts = 3.0
    @State private var copied = false

    private var paintsWithColor: [Paint] {
        library.paints.filter { library.color(of: $0) != nil && !$0.isWhite }
            .sorted { ($0.medium, $0.name, $0.brand) < ($1.medium, $1.name, $1.brand) }
    }
    private var whites: [Paint] {
        library.paints.filter { $0.isWhite && library.color(of: $0) != nil }.sorted { $0.name < $1.name }
    }
    private func swatch(_ id: UUID?) -> Swatch? { swatches.first { $0.id == id } }

    private var result: StrengthMeasure.Result? {
        guard let paint = library.paint(paintID), let white = library.paint(whitePaintID),
              let t = swatch(tintID), let w = swatch(whiteSwatchID), t.id != w.id else { return nil }
        return StrengthMeasure.measure(paint: paint, white: white, paintParts: paintParts, whiteParts: whiteParts,
                                       tintSwatch: (t.red, t.green, t.blue), whiteSwatch: (w.red, w.green, w.blue),
                                       library: library)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Mix the paint with white at a known ratio, and photograph the tint next to a dab of the same white, in even light. Add the photo as a layer (Camera or Photos), and in Color pick one swatch on the tint and one on the white.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Section("From the photo") {
                    swatchPicker("Tint", $tintID)
                    swatchPicker("White", $whiteSwatchID)
                }
                Section("The tint") {
                    Picker("Paint", selection: $paintID) {
                        Text("Choose…").tag("")
                        ForEach(paintsWithColor) { Text("\($0.name) — \($0.brand)").tag($0.id) }
                    }
                    Picker("White", selection: $whitePaintID) {
                        Text("Choose…").tag("")
                        ForEach(whites) { Text("\($0.name) — \($0.brand)").tag($0.id) }
                    }
                    Stepper("Paint: \(parts(paintParts)) part\(paintParts == 1 ? "" : "s")", value: $paintParts, in: 0.5...20, step: 0.5)
                    Stepper("White: \(parts(whiteParts)) part\(whiteParts == 1 ? "" : "s")", value: $whiteParts, in: 0.5...40, step: 0.5)
                }
                if let result, let paint = library.paint(paintID) {
                    resultSection(result, paint: paint)
                }
                measuredSection
            }
            .navigationTitle("Measure strength")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done", action: onDone) } }
        }
        .onAppear {
            if whitePaintID.isEmpty { whitePaintID = whites.first { $0.name.lowercased().contains("titanium") }?.id ?? whites.first?.id ?? "" }
        }
    }

    private func parts(_ v: Double) -> String { v == v.rounded() ? "\(Int(v))" : String(format: "%.1f", v) }

    private func swatchPicker(_ title: String, _ selection: Binding<UUID?>) -> some View {
        Picker(title, selection: selection) {
            Text("Choose…").tag(UUID?.none)
            ForEach(Array(swatches.enumerated()), id: \.element.id) { i, s in
                Text("Swatch \(i + 1)  \(s.hex)").tag(Optional(s.id))
            }
        }
    }

    private func chip(_ c: (Int, Int, Int)) -> some View {
        RoundedRectangle(cornerRadius: 6)
            .fill(Color(red: Double(c.0) / 255, green: Double(c.1) / 255, blue: Double(c.2) / 255))
            .frame(width: 54, height: 40)
    }

    private func resultSection(_ r: StrengthMeasure.Result, paint: Paint) -> some View {
        Section("Result") {
            HStack(spacing: 12) {
                VStack { chip(r.tint); Text("yours").font(.caption2) }
                VStack { chip(r.model); Text("Mixbox").font(.caption2) }
                VStack(alignment: .leading, spacing: 4) {
                    Text(String(format: "Strength %.2f", r.strength)).font(.title3.weight(.semibold))
                    Text("Your \(parts(paintParts)) : \(parts(whiteParts)) looks like Mixbox's \(Mixing.percent(r.effective)) paint.")
                        .font(.caption).foregroundStyle(.secondary)
                    Text(String(format: "Hue off by ΔE %.1f at the same lightness", r.hueOff)
                         + (r.hueOff < 5 ? ": a good fit." : r.hueOff < 10 ? ": the model's hue is somewhat off." : ": the model doesn't fit this paint's tints well."))
                        .font(.caption).foregroundStyle(r.hueOff < 5 ? .green : .orange)
                    if r.clipped {
                        Text("Your tint is outside what the two can mix, so this is a limit, not a measurement. Check the swatches and the white.")
                            .font(.caption).foregroundStyle(.orange)
                    }
                }
            }
            Button("Use strength \(String(format: "%.2f", r.strength)) for \(paint.name)") {
                library.setMeasured(MeasuredStrength(strength: (r.strength * 100).rounded() / 100, paintParts: paintParts,
                                                     whiteParts: whiteParts, whiteName: library.paint(whitePaintID)?.name ?? "",
                                                     hueOff: r.hueOff, date: Date()), for: paint.id)
            }
            .disabled(r.clipped)
            Text(String(format: "Now %.2f (paints.json: %.2f).", paint.strength, library.fileStrength(of: paint)))
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var measuredSection: some View {
        Section("Measured on the iPad") {
            let list = library.measured.compactMap { id, m in library.paint(id).map { ($0, m) } }.sorted { $0.0.name < $1.0.name }
            if list.isEmpty {
                Text("None yet. These are used in mixes here; copy them into the prototype (Edit Paint > Strength).")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ForEach(list, id: \.0.id) { paint, m in
                HStack {
                    VStack(alignment: .leading) {
                        Text("\(paint.name) — \(paint.brand)")
                        Text(String(format: "%.2f · from %@ : %@ with %@, %@ · hue off ΔE %.1f", m.strength, parts(m.paintParts),
                                    parts(m.whiteParts), m.whiteName, m.date.formatted(date: .abbreviated, time: .omitted), m.hueOff))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Remove", role: .destructive) { library.removeMeasured(for: paint.id) }.font(.caption)
                }
            }
            if !list.isEmpty {
                Button(copied ? "Copied" : "Copy the list for the prototype") {
                    UIPasteboard.general.string = list.map { p, m in
                        String(format: "%@ (%@): strength %.2f", p.name, p.brand, m.strength)
                    }.joined(separator: "\n")
                    copied = true
                }
            }
        }
    }
}
