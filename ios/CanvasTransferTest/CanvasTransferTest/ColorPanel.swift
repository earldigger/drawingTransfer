import SwiftUI
import UniformTypeIdentifiers

/// The Color workspace's right-hand panel for the selected swatch (the
/// design's Details | Paints & mixes): what the color is, and how to mix it
/// from your paints with Mixbox.
struct ColorPanel: View {
    let swatch: Swatch
    let number: Int
    var onClose: () -> Void

    enum Tab: String, CaseIterable, Identifiable {
        case details = "Details"
        case mixes = "Paints & mixes"
        var id: String { rawValue }
    }

    @AppStorage("colorPanelTab") private var tab = Tab.mixes

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("\(number)")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(swatch.labelColor)
                    .frame(width: 26, height: 26)
                    .background(RoundedRectangle(cornerRadius: 6).fill(swatch.color))
                Text("Swatch \(number)").font(.headline)
                Spacer()
                Button(action: onClose) { Image(systemName: "xmark.circle.fill").font(.title3) }
                    .foregroundStyle(.secondary)
                    .accessibilityLabel("Close")
            }
            Picker("Tab", selection: $tab) {
                ForEach(Tab.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            ScrollView {
                switch tab {
                case .details: SwatchDetails(swatch: swatch)
                case .mixes: MixesView(swatch: swatch)
                }
            }
        }
        .padding(14)
        .frame(width: 350)
        .frame(maxHeight: 600)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.97)))
    }
}

// MARK: - Details

/// Hex, RGB, Lab, value, warm or cool, the complement, and Mixbox tints,
/// shades and tones (the prototype's Swatch details).
struct SwatchDetails: View {
    let swatch: Swatch

    static let mixSteps = [0.0, 0.2, 0.4, 0.6, 0.8, 0.94]  // the share of white, black or gray added (MIX_STEPS)

    var body: some View {
        let rgb = (swatch.red, swatch.green, swatch.blue)
        let lab = PaintColor.lab(rgb)
        VStack(alignment: .leading, spacing: 12) {
            RoundedRectangle(cornerRadius: 10).fill(swatch.color).frame(height: 64)
            grid([("Hex", swatch.hex), ("RGB", "\(swatch.red), \(swatch.green), \(swatch.blue)"),
                  ("Lab (D50)", String(format: "%.1f, %.1f, %.1f", lab.L, lab.a, lab.b)),
                  ("Value", String(format: "%.0f of 100 (L*)", swatch.value)),
                  ("Temperature", Self.temperature(rgb))])
            row("Complement", [Self.complement(rgb)])
            row("Tints (+ white)", Self.mixSteps.map { Mixbox.lerp(rgb, (255, 255, 255), $0) })
            row("Shades (+ black)", Self.mixSteps.map { Mixbox.lerp(rgb, (0, 0, 0), $0) })
            row("Tones (+ gray)", Self.mixSteps.map { Mixbox.lerp(rgb, (128, 128, 128), $0) })
            Text("Tints, shades and tones are mixed with Mixbox, as with paint, not on screen.")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func grid(_ rows: [(String, String)]) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
            ForEach(rows, id: \.0) { row in
                GridRow {
                    Text(row.0).foregroundStyle(.secondary)
                    Text(row.1).monospacedDigit().textSelection(.enabled)
                }
            }
        }
        .font(.callout)
    }

    private func row(_ title: String, _ colors: [(Int, Int, Int)]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 3) {
                ForEach(colors.indices, id: \.self) { i in
                    let c = colors[i]
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color(red: Double(c.0) / 255, green: Double(c.1) / 255, blue: Double(c.2) / 255))
                        .frame(width: 44, height: 30)
                }
            }
        }
    }

    /// Warm (+1) to cool (-1), as in the prototype: warmest near orange,
    /// coolest near cyan-blue, muted colors pulled toward neutral.
    static func temperature(_ rgb: (Int, Int, Int)) -> String {
        let lab = ColorStudy.lab(UInt8(rgb.0), UInt8(rgb.1), UInt8(rgb.2))  // D65
        let chroma = hypot(Double(lab.y), Double(lab.z)), hue = atan2(Double(lab.z), Double(lab.y)) * 180 / .pi
        let score = cos((hue - 55) * .pi / 180) * min(1, chroma / 40)
        let label = score < -0.6 ? "Very cool" : score < -0.2 ? "Cool" : score < 0.2 ? "Neutral" : score < 0.6 ? "Warm" : "Very warm"
        return "\(label) (\(String(format: "%+.2f", score)))"
    }

    /// The opposite hue at the same lightness (Lab D65), with chroma cut only
    /// as far as needed to fit on screen.
    static func complement(_ rgb: (Int, Int, Int)) -> (Int, Int, Int) {
        let lab = ColorStudy.lab(UInt8(rgb.0), UInt8(rgb.1), UInt8(rgb.2))
        func srgb(_ scale: Double) -> (Double, Double, Double) {
            let L = Double(lab.x), a = -Double(lab.y) * scale, b = -Double(lab.z) * scale
            let fy = (L + 16) / 116, fx = fy + a / 500, fz = fy - b / 200
            func inv(_ t: Double) -> Double { t * t * t > 216.0 / 24389 ? t * t * t : (116 * t - 16) * 27 / 24389 }
            let x = inv(fx) * 0.95047, y = inv(fy), z = inv(fz) * 1.08883
            let lin = (3.2406 * x - 1.5372 * y - 0.4986 * z, -0.9689 * x + 1.8758 * y + 0.0415 * z,
                       0.0557 * x - 0.2040 * y + 1.0570 * z)
            func g(_ v: Double) -> Double { v <= 0.0031308 ? 12.92 * v : 1.055 * pow(v, 1 / 2.4) - 0.055 }
            return (g(lin.0), g(lin.1), g(lin.2))
        }
        func fits(_ c: (Double, Double, Double)) -> Bool { [c.0, c.1, c.2].allSatisfy { $0 >= -1e-4 && $0 <= 1 + 1e-4 } }
        var out = srgb(1)
        if !fits(out) {
            var lo = 0.0, hi = 1.0
            for _ in 0..<18 {
                let mid = (lo + hi) / 2
                if fits(srgb(mid)) { lo = mid } else { hi = mid }
            }
            out = srgb(lo)
        }
        func byte(_ v: Double) -> Int { Int((min(max(v.isNaN ? 0 : v, 0), 1) * 255).rounded()) }
        return (byte(out.0), byte(out.1), byte(out.2))
    }
}

// MARK: - Paints & mixes

/// Mix from (a palette, or all your enabled paints of a medium) and Lighten
/// with (a white, water, or nothing), then the best one-paint and two-paint
/// recipes, as in the prototype's Paints panel.
struct MixesView: View {
    let swatch: Swatch

    @State private var library = PaintLibrary.shared
    @AppStorage("mixFrom") private var mixFrom = ""  // "medium:oil" or "palette:<id>"
    @AppStorage("lightenWith") private var lightenWith = ""  // a paint id, "water" or "none"; "" = the first white
    @State private var result: Mixing.Result? = nil
    @State private var working = false
    @State private var importing = false
    @State private var importError: String? = nil

    private struct Source: Identifiable {
        let key: String, title: String, medium: String, paints: [Paint]
        var id: String { key }
    }

    private var sources: [Source] {
        let media = library.media.map { m -> Source in
            let paints = library.paints.filter { $0.medium == m && $0.enabled }
            let withColor = paints.filter { library.color(of: $0) != nil }.count
            return Source(key: "medium:\(m)", title: "All \(m) paints (\(withColor) with color)", medium: m, paints: paints)
        }
        let palettes = library.palettes.map {
            Source(key: "palette:\($0.id)", title: "\($0.name) (\($0.medium), \($0.paintIDs.count))", medium: $0.medium,
                   paints: library.paints(of: $0))
        }
        return palettes + media  // your palettes first
    }

    private var source: Source? { sources.first { $0.key == mixFrom } ?? sources.first }

    private var whites: [Paint] {
        guard let source else { return [] }
        return library.whites(medium: source.medium, selection: source.paints)
    }

    /// The chosen lightener; by default a white (the selection's own first), or water for watercolor.
    private var lightener: Paint? {
        switch lightenWith {
        case "none": return nil
        case "water": return Mixing.water
        default:
            if let chosen = whites.first(where: { $0.id == lightenWith }) { return chosen }
            return source?.medium == "watercolor" || whites.isEmpty ? Mixing.water : whites.first
        }
    }

    private var searchKey: String {
        "\(swatch.red),\(swatch.green),\(swatch.blue) \(source?.key ?? "") \(lightener?.id ?? "none") \(library.paints.count) \(library.origin)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if library.paints.isEmpty {
                Text("No paints. Import your paints.json from the prototype.").font(.callout)
            } else {
                settings
                if let source, let missing = Optional(source.paints.filter { library.color(of: $0) == nil }), !missing.isEmpty {
                    Text("No color data (left out): " + missing.map(\.name).joined(separator: ", "))
                        .font(.caption2).foregroundStyle(.secondary)
                }
                if working && result == nil {
                    ProgressView().frame(maxWidth: .infinity)
                } else if let result {
                    section("One paint", result.singles)
                    section("Two paints", result.pairs)
                }
                Text("Amounts are a guide, not a recipe: Mixbox, with each paint's strength. ΔE is CIEDE2000; about 1 is just visible.")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Divider()
            HStack {
                Text("\(library.paints.count) paints · \(library.origin)").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Import paints…") { importing = true }.font(.caption)
            }
            if let importError { Text(importError).font(.caption).foregroundStyle(.red) }
        }
        .task(id: searchKey) { await search() }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.json]) { picked in
            do {
                try library.importFile(at: picked.get())
                importError = nil
            } catch {
                importError = "That isn't a paints.json from the prototype."
            }
        }
    }

    private var settings: some View {
        Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 6) {
            GridRow {
                Text("Mix from").foregroundStyle(.secondary)
                Picker("Mix from", selection: Binding(get: { source?.key ?? "" }, set: { mixFrom = $0; lightenWith = "" })) {
                    ForEach(sources) { Text($0.title).tag($0.key) }
                }
                .pickerStyle(.menu)
            }
            GridRow {
                Text("Lighten with").foregroundStyle(.secondary)
                Picker("Lighten with", selection: Binding(get: { lightener?.id ?? "none" }, set: { lightenWith = $0 })) {
                    ForEach(whites) { Text("\($0.name) — \($0.brand)").tag($0.id) }
                    Text("Water (paper white)").tag("water")
                    Text("Nothing").tag("none")
                }
                .pickerStyle(.menu)
            }
        }
        .font(.callout)
    }

    private func section(_ title: String, _ recipes: [Mixing.Recipe]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.subheadline.weight(.semibold))
            if recipes.isEmpty {
                Text("Nothing to mix from.").font(.caption).foregroundStyle(.secondary)
            }
            ForEach(recipes) { recipe in
                RecipeRow(swatch: swatch, recipe: recipe)
            }
        }
    }

    private func search() async {
        guard let source else { result = nil; return }
        working = true
        let target = (swatch.red, swatch.green, swatch.blue), paints = source.paints, white = lightener, lib = library
        let found = await Task.detached(priority: .userInitiated) {
            Mixing.find(target, paints: paints, lightener: white, library: lib)
        }.value
        guard !Task.isCancelled else { return }
        result = found
        working = false
    }
}

/// One recipe: your color and the mix side by side (halves touching, so the
/// shift shows), a line per paint led by its amount, then ΔE and how close.
struct RecipeRow: View {
    let swatch: Swatch
    let recipe: Mixing.Recipe

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            HStack(spacing: 0) {
                Rectangle().fill(swatch.color)
                Rectangle().fill(Color(red: Double(recipe.rgb.0) / 255, green: Double(recipe.rgb.1) / 255,
                                       blue: Double(recipe.rgb.2) / 255))
            }
            .frame(width: 76, height: 52)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(alignment: .bottom) {
                HStack {
                    Text("yours"); Spacer(); Text("mix")
                }
                .font(.system(size: 8)).foregroundStyle(.white).shadow(radius: 1).padding(.horizontal, 4).padding(.bottom, 2)
            }
            VStack(alignment: .leading, spacing: 2) {
                ForEach(recipe.parts.indices, id: \.self) { i in
                    let part = recipe.parts[i]
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(Mixing.percent(part.share)).monospacedDigit().frame(width: 38, alignment: .trailing)
                            .font(.callout.weight(.semibold))
                        VStack(alignment: .leading, spacing: 0) {
                            Text(part.paint.name).font(.callout).lineLimit(1)
                            if !part.paint.brand.isEmpty {
                                Text(part.paint.brand).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                    }
                }
                Text(String(format: "ΔE %.1f · %@", recipe.deltaE, Mixing.closeness(recipe.deltaE)))
                    .font(.caption).foregroundStyle(recipe.deltaE < 5 ? .green : .secondary)
                ForEach(recipe.standIns.indices, id: \.self) { i in
                    let s = recipe.standIns[i]
                    Text("\(s.paint.name) mixed as \(s.from.name) (\(s.from.brand))").font(.caption2).foregroundStyle(.secondary)
                }
                if !recipe.offScreen.isEmpty {
                    Text("Beyond the screen's colors, shown clipped: " + recipe.offScreen.map(\.name).joined(separator: ", "))
                        .font(.caption2).foregroundStyle(.orange)
                }
            }
        }
        .padding(.vertical, 2)
    }
}
