import Foundation

/// CIELAB under D50 (how artistpigments.org lists paints), to and from sRGB
/// with Bradford adaptation, and CIEDE2000: the prototype's color_study.py.
enum PaintColor {
    typealias Lab = (L: Double, a: Double, b: Double)

    private static func xyz(_ x: Double, _ y: Double) -> (Double, Double, Double) { (x / y, 1, (1 - x - y) / y) }
    private static let d65 = xyz(0.3127, 0.3290)
    private static let d50 = xyz(0.3457, 0.3585)

    /// Linear sRGB → XYZ (D50), and back: the sRGB primaries, adapted to D50 with Bradford.
    private static let toXYZ: [[Double]] = {
        // sRGB to XYZ (D65) from its primaries and white.
        let p = [xyz(0.64, 0.33), xyz(0.30, 0.60), xyz(0.15, 0.06)]
        let m = [[p[0].0, p[1].0, p[2].0], [p[0].1, p[1].1, p[2].1], [p[0].2, p[1].2, p[2].2]]
        let s = multiply(invert(m), [[d65.0], [d65.1], [d65.2]])
        let srgb = (0..<3).map { r in (0..<3).map { c in m[r][c] * s[c][0] } }
        // Bradford: D65 → D50.
        let bradford = [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]]
        let src = multiply(bradford, [[d65.0], [d65.1], [d65.2]]), dst = multiply(bradford, [[d50.0], [d50.1], [d50.2]])
        let scale = [[dst[0][0] / src[0][0], 0, 0], [0, dst[1][0] / src[1][0], 0], [0, 0, dst[2][0] / src[2][0]]]
        let adapt = multiply(invert(bradford), multiply(scale, bradford))
        return multiply(adapt, srgb)
    }()
    private static let fromXYZ = invert(toXYZ)

    /// sRGB 0...1 to Lab (D50): srgb_to_lab_d50.
    static func lab(_ r: Double, _ g: Double, _ b: Double) -> Lab {
        func lin(_ s: Double) -> Double { s <= 0.04045 ? s / 12.92 : pow((s + 0.055) / 1.055, 2.4) }
        let R = lin(r), G = lin(g), B = lin(b), m = toXYZ
        let t = [(m[0][0] * R + m[0][1] * G + m[0][2] * B) / d50.0,
                 (m[1][0] * R + m[1][1] * G + m[1][2] * B) / d50.1,
                 (m[2][0] * R + m[2][1] * G + m[2][2] * B) / d50.2]
        let e: Double = pow(6.0 / 29, 3), k: Double = 3 * pow(6.0 / 29, 2)
        let f = t.map { (v: Double) -> Double in v > e ? cbrt(v) : v / k + 4.0 / 29 }
        return (116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2]))
    }

    static func lab(_ rgb: (Int, Int, Int)) -> Lab { lab(Double(rgb.0) / 255, Double(rgb.1) / 255, Double(rgb.2) / 255) }

    /// The screen color for a Lab (D50), clipped, and whether it fits on screen: lab_d50_to_srgb.
    static func srgb(_ lab: [Double]) -> (rgb: (Int, Int, Int), inGamut: Bool) {
        let fy = (lab[0] + 16) / 116, fx = fy + lab[1] / 500, fz = fy - lab[2] / 200
        func inv(_ f: Double) -> Double { f > 6.0 / 29 ? f * f * f : 3 * pow(6.0 / 29, 2) * (f - 4.0 / 29) }
        let X = inv(fx) * d50.0, Y = inv(fy) * d50.1, Z = inv(fz) * d50.2, m = fromXYZ
        let linear = [m[0][0] * X + m[0][1] * Y + m[0][2] * Z, m[1][0] * X + m[1][1] * Y + m[1][2] * Z,
                      m[2][0] * X + m[2][1] * Y + m[2][2] * Z]
        let encoded = linear.map { v -> Double in
            let s = v <= 0.0031308 ? 12.92 * v : 1.055 * pow(v, 1 / 2.4) - 0.055
            return v < 0 ? -1.055 * pow(-v, 1 / 2.4) + 0.055 : s  // keep the sign, to judge the gamut
        }
        let inGamut = encoded.allSatisfy { $0 >= -0.5 / 255 && $0 <= 1 + 0.5 / 255 }
        let c = encoded.map { Int((min(max($0, 0), 1) * 255).rounded()) }
        return ((c[0], c[1], c[2]), inGamut)
    }

    /// CIEDE2000 color difference; about 1 is just visible side by side.
    static func deltaE(_ x: Lab, _ y: Lab) -> Double {
        let c1 = hypot(x.a, x.b), c2 = hypot(y.a, y.b), cBar = (c1 + c2) / 2
        let g = 0.5 * (1 - sqrt(pow(cBar, 7) / (pow(cBar, 7) + pow(25, 7))))
        let a1 = (1 + g) * x.a, a2 = (1 + g) * y.a
        let cp1 = hypot(a1, x.b), cp2 = hypot(a2, y.b)
        func hue(_ b: Double, _ a: Double) -> Double {
            guard a != 0 || b != 0 else { return 0 }
            let h = atan2(b, a) * 180 / .pi
            return h < 0 ? h + 360 : h
        }
        let h1 = hue(x.b, a1), h2 = hue(y.b, a2)
        let dL = y.L - x.L, dC = cp2 - cp1
        var dh = 0.0
        if cp1 * cp2 != 0 {
            dh = h2 - h1
            if dh > 180 { dh -= 360 } else if dh < -180 { dh += 360 }
        }
        let dH = 2 * sqrt(cp1 * cp2) * sin(dh * .pi / 360)
        let lBar = (x.L + y.L) / 2, cpBar = (cp1 + cp2) / 2
        var hBar = h1 + h2
        if cp1 * cp2 != 0 {
            if abs(h1 - h2) <= 180 { hBar /= 2 } else { hBar = h1 + h2 < 360 ? (h1 + h2 + 360) / 2 : (h1 + h2 - 360) / 2 }
        }
        func rad(_ d: Double) -> Double { d * .pi / 180 }
        let t = 1 - 0.17 * cos(rad(hBar - 30)) + 0.24 * cos(rad(2 * hBar)) + 0.32 * cos(rad(3 * hBar + 6))
            - 0.20 * cos(rad(4 * hBar - 63))
        let dTheta = 30 * exp(-pow((hBar - 275) / 25, 2))
        let rc = 2 * sqrt(pow(cpBar, 7) / (pow(cpBar, 7) + pow(25, 7)))
        let sl = 1 + 0.015 * pow(lBar - 50, 2) / sqrt(20 + pow(lBar - 50, 2))
        let sc = 1 + 0.045 * cpBar, sh = 1 + 0.015 * cpBar * t
        let rt = -sin(rad(2 * dTheta)) * rc
        let l = dL / sl, c = dC / sc, h = dH / sh
        return sqrt(l * l + c * c + h * h + rt * c * h)
    }

    // MARK: 3 × 3 matrices

    private static func multiply(_ a: [[Double]], _ b: [[Double]]) -> [[Double]] {
        (0..<a.count).map { i in (0..<b[0].count).map { j in (0..<b.count).reduce(0) { $0 + a[i][$1] * b[$1][j] } } }
    }

    private static func invert(_ m: [[Double]]) -> [[Double]] {
        let a = m[0][0], b = m[0][1], c = m[0][2], d = m[1][0], e = m[1][1], f = m[1][2], g = m[2][0], h = m[2][1], i = m[2][2]
        let det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
        return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
                [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
                [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]
    }
}

/// Matching a color to your paints with Mixbox (find_recipes in the
/// prototype's mixing.py): one paint lightened in 1 % steps, and two paints
/// plus the lightener on a 10 % grid over every pair, refined in 1 % steps
/// around the best twenty. Ranked by CIEDE2000; among recipes that match
/// within 1, those built on a paint already close on its own come first.
/// Amounts are real amounts: what each paint should contribute ÷ its strength.
enum Mixing {
    static let water = Paint(id: "water", medium: "", brand: "", name: "Water (paper white)", lab: [100, 0, 0])
    static let top = 5
    private static let coarseSteps = 10
    private static let refinePairs = 20
    private static let refineSpan = 0.1

    struct Recipe: Identifiable {
        let id = UUID()
        var parts: [(paint: Paint, share: Double)]  // real amounts, adding up to 1; main color first, lightener last
        var rgb: (Int, Int, Int)  // what it makes
        var deltaE: Double
        var offScreen: [Paint]  // colors clipped to the screen before mixing
        var standIns: [(paint: Paint, from: Paint)]  // paints mixed with another paint's color
    }

    struct Result {
        var singles: [Recipe]
        var pairs: [Recipe]
    }

    static func closeness(_ deltaE: Double) -> String {
        deltaE < 2 ? "very close" : deltaE < 5 ? "close" : deltaE < 10 ? "noticeably different" : "far off"
    }

    static func percent(_ share: Double) -> String {
        share > 0 && share < 0.005 ? "<1%" : "\(Int((share * 100).rounded()))%"
    }

    /// Real amounts from what each paint should contribute (real_shares).
    static func realShares(strengths: [Double], effective: [Double]) -> [Double] {
        let amounts = zip(strengths, effective).map { $1 / max($0, 1e-6) }
        let total = amounts.reduce(0, +)
        return amounts.map { $0 / (total == 0 ? 1 : total) }
    }

    /// The paints being searched: screen color, latent, strength. Paints with
    /// the same color data are searched once.
    private struct Entry {
        var paint: Paint
        var rgb: (Int, Int, Int)
        var offScreen: Bool
        var standIn: Paint?
        var latent: Mixbox.Latent
    }

    private static func entries(_ paints: [Paint], library: PaintLibrary) -> [Entry] {
        var out: [Entry] = []
        var seen = Set<String>()
        for paint in paints.sorted(by: { ($0.lab == nil ? 1 : 0) < ($1.lab == nil ? 1 : 0) }) {  // measured first
            guard let lab = paint.id == water.id ? paint.lab : library.color(of: paint) else { continue }
            let key = lab.map { String(format: "%.3f", $0) }.joined(separator: ",")
            if seen.contains(key) && paint.id != water.id { continue }
            seen.insert(key)
            let screen = PaintColor.srgb(lab)
            out.append(Entry(paint: paint, rgb: screen.rgb, offScreen: !screen.inGamut,
                             standIn: paint.lab == nil ? library.standInUsed(for: paint) : nil,
                             latent: Mixbox.latent(Double(screen.rgb.0) / 255, Double(screen.rgb.1) / 255, Double(screen.rgb.2) / 255)))
        }
        return out
    }

    private static func score(_ z: Mixbox.Latent, _ target: PaintColor.Lab) -> (Double, (Double, Double, Double)) {
        let rgb = Mixbox.rgb(z)
        return (PaintColor.deltaE(PaintColor.lab(rgb.0, rgb.1, rgb.2), target), rgb)
    }

    private static func recipe(_ list: [Entry], _ indices: [Int], _ shares: [Double], _ rgb: (Double, Double, Double),
                               _ deltaE: Double) -> Recipe {
        let used = zip(indices, shares).filter { $0.1 >= 0.005 }
        let real = realShares(strengths: used.map { list[$0.0].paint.strength }, effective: used.map(\.1))
        let entries = used.map { list[$0.0] }
        return Recipe(parts: zip(entries, real).map { ($0.paint, $1) },
                      rgb: (Int((rgb.0 * 255).rounded()), Int((rgb.1 * 255).rounded()), Int((rgb.2 * 255).rounded())),
                      deltaE: deltaE, offScreen: entries.filter(\.offScreen).map(\.paint),
                      standIns: entries.compactMap { e in e.standIn.map { (e.paint, $0) } })
    }

    /// The best one-paint and two-paint recipes for `target` from `paints`,
    /// each lightened with `lightener` (a white, `water`, or nil).
    static func find(_ target: (Int, Int, Int), paints: [Paint], lightener: Paint?, library: PaintLibrary) -> Result {
        let colors = paints.filter { $0.id != lightener?.id && !(lightener != nil && $0.isWhite) }
        var list = entries(colors, library: library)
        let n = list.count
        guard n > 0, Mixbox.isAvailable else { return Result(singles: [], pairs: []) }
        if let lightener, let white = entries([lightener], library: library).first { list.append(white) }
        let hasWhite = list.count > n
        let zw: Mixbox.Latent = hasWhite ? list[n].latent : (0, 0, 0, 0, 0, 0, 0)
        let goal = PaintColor.lab(target)

        // One paint (+ white).
        let steps = hasWhite ? (1...100).map { Double($0) / 100 } : [1.0]
        var alone = [Double](repeating: .infinity, count: n)
        var bestSingle: [(share: Double, de: Double, rgb: (Double, Double, Double))] = []
        for i in 0..<n {
            var best = (share: 1.0, de: Double.infinity, rgb: (0.0, 0.0, 0.0))
            for a in steps {
                let (de, rgb) = score(Mixbox.sum([(list[i].latent, a), (zw, 1 - a)]), goal)
                if de < best.de { best = (a, de, rgb) }
            }
            alone[i] = best.de
            bestSingle.append(best)
        }
        let singles = (0..<n).sorted { alone[$0] < alone[$1] }.prefix(top).map { i -> Recipe in
            let b = bestSingle[i]
            return hasWhite ? recipe(list, [i, n], [b.share, 1 - b.share], b.rgb, b.de) : recipe(list, [i], [1], b.rgb, b.de)
        }

        // Two paints (+ white): a coarse grid over every pair, then 1 % steps around the best.
        var pairs: [Recipe] = []
        if n >= 2 {
            var grid: [(Double, Double)] = []
            for i in 1..<coarseSteps {
                for j in 1..<coarseSteps where hasWhite ? i + j <= coarseSteps : i + j == coarseSteps {
                    grid.append((Double(i) / Double(coarseSteps), Double(j) / Double(coarseSteps)))
                }
            }
            var coarse: [(i: Int, j: Int, de: Double, a: Double, b: Double)] = []
            for i in 0..<n {
                for j in (i + 1)..<n {
                    var best = (de: Double.infinity, a: 0.0, b: 0.0)
                    for (a, b) in grid {
                        let (de, _) = score(Mixbox.sum([(list[i].latent, a), (list[j].latent, b), (zw, max(1 - a - b, 0))]), goal)
                        if de < best.de { best = (de, a, b) }
                    }
                    coarse.append((i, j, best.de, best.a, best.b))
                }
            }
            var refined: [(key: Double, tie: Double, recipe: Recipe)] = []
            for c in coarse.sorted(by: { $0.de < $1.de }).prefix(refinePairs) {
                var best = (de: Double.infinity, a: 0.0, b: 0.0, rgb: (0.0, 0.0, 0.0))
                for da in -10...10 {
                    for db in -10...10 {
                        let a = ((c.a + Double(da) / 100) * 100).rounded() / 100, b = ((c.b + Double(db) / 100) * 100).rounded() / 100
                        guard a >= 0.01, b >= 0.01, hasWhite ? a + b <= 1 + 1e-9 : abs(a + b - 1) < 1e-9 else { continue }
                        let (de, rgb) = score(Mixbox.sum([(list[c.i].latent, a), (list[c.j].latent, b), (zw, max(1 - a - b, 0))]), goal)
                        if de < best.de { best = (de, a, b, rgb) }
                    }
                }
                var indices = [c.i, c.j], shares = [best.a, best.b]
                if hasWhite { indices.append(n); shares.append(max(0, 1 - best.a - best.b)) }
                var r = recipe(list, indices, shares, best.rgb, best.de)
                // Main color first, the lightener last.
                let lightenerID = hasWhite ? list[n].paint.id : nil
                r.parts = r.parts.filter { $0.paint.id != lightenerID }.sorted { $0.share > $1.share }
                    + r.parts.filter { $0.paint.id == lightenerID }
                refined.append((max(best.de, 1), min(alone[c.i], alone[c.j]), r))
            }
            pairs = refined.sorted { ($0.key, $0.tie) < ($1.key, $1.tie) }.prefix(top).map(\.recipe)
        }
        return Result(singles: Array(singles), pairs: pairs)
    }
}
