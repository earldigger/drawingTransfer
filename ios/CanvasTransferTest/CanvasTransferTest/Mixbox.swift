// ==========================================================
//  MIXBOX 2.0 (c) 2022 Secret Weapons. All rights reserved.
//  License: Creative Commons Attribution-NonCommercial 4.0
//  Authors: Sarka Sochorova and Ondrej Jamriska
// ==========================================================
//  A Swift port of the pymixbox 2.0 the prototype uses (mixbox.py), for
//  personal use only (see CLAUDE.md). mixbox_lut.bin is that package's
//  lookup table, decompressed: 64 × 64 × 64 × 3 bytes after a 192-byte lead.

import Foundation

/// Natural paint mixing: a color is turned into a 7-number latent (amounts of
/// four pigments, plus what they don't explain), latents are mixed by
/// weighted sums, and the result turned back into a color.
enum Mixbox {
    static let latentSize = 7
    typealias Latent = (Double, Double, Double, Double, Double, Double, Double)

    private static let lut: [UInt8] = {
        guard let url = Bundle.main.url(forResource: "mixbox_lut", withExtension: "bin"),
              let data = try? Data(contentsOf: url) else { return [] }
        return [UInt8](data)
    }()

    static var isAvailable: Bool { lut.count >= 790_000 }

    /// sRGB 0...1 to a latent (float_rgb_to_latent).
    static func latent(_ r: Double, _ g: Double, _ b: Double) -> Latent {
        let r = clamp(r), g = clamp(g), b = clamp(b)
        let x = r * 63, y = g * 63, z = b * 63
        let ix = Int(x), iy = Int(y), iz = Int(z)
        let tx = x - Double(ix), ty = y - Double(iy), tz = z - Double(iz)
        let xyz = (ix + iy * 64 + iz * 64 * 64) & 0x3FFFF
        var c0 = 0.0, c1 = 0.0, c2 = 0.0
        lut.withUnsafeBufferPointer { l in
            func add(_ w: Double, _ o: Int) {
                c0 += w * Double(l[xyz + o]); c1 += w * Double(l[xyz + o + 262_144]); c2 += w * Double(l[xyz + o + 524_288])
            }
            add((1 - tx) * (1 - ty) * (1 - tz), 192)
            add(tx * (1 - ty) * (1 - tz), 193)
            add((1 - tx) * ty * (1 - tz), 256)
            add(tx * ty * (1 - tz), 257)
            add((1 - tx) * (1 - ty) * tz, 4288)
            add(tx * (1 - ty) * tz, 4289)
            add((1 - tx) * ty * tz, 4352)
            add(tx * ty * tz, 4353)
        }
        c0 /= 255; c1 /= 255; c2 /= 255
        let c3 = 1 - (c0 + c1 + c2)
        let mix = polynomial(c0, c1, c2, c3)
        return (c0, c1, c2, c3, r - mix.0, g - mix.1, b - mix.2)
    }

    /// A latent back to sRGB 0...1 (latent_to_float_rgb).
    static func rgb(_ z: Latent) -> (Double, Double, Double) {
        let p = polynomial(z.0, z.1, z.2, z.3)
        return (clamp(p.0 + z.4), clamp(p.1 + z.5), clamp(p.2 + z.6))
    }

    /// Two colors mixed, `t` of the second (lerp), in 0...255.
    static func lerp(_ a: (Int, Int, Int), _ b: (Int, Int, Int), _ t: Double) -> (Int, Int, Int) {
        let za = latent(Double(a.0) / 255, Double(a.1) / 255, Double(a.2) / 255)
        let zb = latent(Double(b.0) / 255, Double(b.1) / 255, Double(b.2) / 255)
        let m = rgb(sum([(za, 1 - t), (zb, t)]))
        return (Int((m.0 * 255).rounded()), Int((m.1 * 255).rounded()), Int((m.2 * 255).rounded()))
    }

    /// Σ weight × latent.
    static func sum(_ parts: [(Latent, Double)]) -> Latent {
        var s: Latent = (0, 0, 0, 0, 0, 0, 0)
        for (z, w) in parts {
            s.0 += w * z.0; s.1 += w * z.1; s.2 += w * z.2; s.3 += w * z.3
            s.4 += w * z.4; s.5 += w * z.5; s.6 += w * z.6
        }
        return s
    }

    private static func clamp(_ x: Double) -> Double { min(max(x, 0), 1) }

    private static func polynomial(_ c0: Double, _ c1: Double, _ c2: Double, _ c3: Double) -> (Double, Double, Double) {
        var r = 0.0, g = 0.0, b = 0.0
        let c00 = c0 * c0, c11 = c1 * c1, c22 = c2 * c2, c33 = c3 * c3
        let c01 = c0 * c1, c02 = c0 * c2, c12 = c1 * c2
        func t(_ w: Double, _ a: Double, _ bb: Double, _ c: Double) { r += a * w; g += bb * w; b += c * w }
        t(c0 * c00, 0.07717053, 0.02826978, 0.24832992)
        t(c1 * c11, 0.95912302, 0.80256528, 0.03561839)
        t(c2 * c22, 0.74683774, 0.04868586, 0.00000000)
        t(c3 * c33, 0.99518138, 0.99978149, 0.99704802)
        t(c00 * c1, 0.04819146, 0.83363781, 0.32515377)
        t(c01 * c1, -0.68146950, 1.46107803, 1.06980936)
        t(c00 * c2, 0.27058419, -0.15324870, 1.98735057)
        t(c02 * c2, 0.80478189, 0.67093710, 0.18424500)
        t(c00 * c3, -0.35031003, 1.37855826, 3.68865000)
        t(c0 * c33, 1.05128046, 1.97815239, 2.82989073)
        t(c11 * c2, 3.21607125, 0.81270228, 1.03384539)
        t(c1 * c22, 2.78893374, 0.41565549, -0.04487295)
        t(c11 * c3, 3.02162577, 2.55374103, 0.32766114)
        t(c1 * c33, 2.95124691, 2.81201112, 1.17578442)
        t(c22 * c3, 2.82677043, 0.79933038, 1.81715262)
        t(c2 * c33, 2.99691099, 1.22593053, 1.80653661)
        t(c01 * c2, 1.87394106, 2.05027182, -0.29835996)
        t(c01 * c3, 2.56609566, 7.03428198, 0.62575374)
        t(c02 * c3, 4.08329484, -1.40408358, 2.14995522)
        t(c12 * c3, 6.00078678, 2.55552042, 1.90739502)
        return (r, g, b)
    }
}
