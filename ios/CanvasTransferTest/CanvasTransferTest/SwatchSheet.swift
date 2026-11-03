import SwiftUI
import UIKit

/// The swatch sheet (decision D: "Also: share a swatch sheet"): a PDF to
/// print or keep at the easel. The canvas with its numbered swatches, then
/// each swatch's color and numbers and its best mixes from your paints, with
/// the Mix from and Lighten with chosen in the Color panel.
enum SwatchSheet {
    private static let page = CGRect(x: 0, y: 0, width: 612, height: 792)  // US Letter, in points
    private static let margin: CGFloat = 40

    @MainActor
    static func render(_ session: TransferSession) -> URL? {
        let library = PaintLibrary.shared, defaults = UserDefaults.standard
        let source = library.mixSource(defaults.string(forKey: "mixFrom") ?? "",
                                       favoritesOnly: defaults.bool(forKey: "mixFavoritesOnly"))
        let lightener = library.lightener(defaults.string(forKey: "lightenWith") ?? "", for: source)
        let picture = canvasPicture(session)
        let recipes = session.swatches.map { s in
            source.map { Mixing.find((s.red, s.green, s.blue), paints: $0.paints, lightener: lightener, library: library) }
        }

        let renderer = UIGraphicsPDFRenderer(bounds: page)
        let data = renderer.pdfData { context in
            context.beginPage()
            var y = margin
            let inches = "\(Int(session.canvasSize.width)) × \(Int(session.canvasSize.height)) in"
            y = text("Swatches", at: CGPoint(x: margin, y: y), font: .boldSystemFont(ofSize: 22))
            y = text("\(inches) · \(Date().formatted(date: .long, time: .shortened))",
                     at: CGPoint(x: margin, y: y + 2), font: .systemFont(ofSize: 11), color: .darkGray)
            if let picture {
                let fit = fitRect(picture.size, in: CGSize(width: page.width - 2 * margin, height: 300))
                let rect = CGRect(x: margin, y: y + 12, width: fit.width, height: fit.height)
                picture.draw(in: rect)
                UIColor.lightGray.setStroke()
                UIBezierPath(rect: rect).stroke()
                y = rect.maxY + 18
            }
            let mixing = source.map { "Mixes from \($0.title), lightened with \(lightener?.name ?? "nothing"). Mixbox; amounts are a guide, corrected for each paint's strength." }
                ?? "No paints to mix from."
            y = text(mixing, at: CGPoint(x: margin, y: y), width: page.width - 2 * margin, font: .systemFont(ofSize: 9), color: .darkGray) + 10

            for (i, swatch) in session.swatches.enumerated() {
                let height: CGFloat = 92
                if y + height > page.height - margin {
                    context.beginPage()
                    y = margin
                }
                drawSwatch(swatch, number: i + 1, result: recipes[i], at: y)
                y += height
            }
        }
        let url = URL.temporaryDirectory.appending(path: "Swatches \(Int(session.canvasSize.width))x\(Int(session.canvasSize.height)) in.pdf")
        do {
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            return nil
        }
    }

    /// The canvas as shown, with the swatch markers on it.
    @MainActor
    private static func canvasPicture(_ session: TransferSession) -> UIImage? {
        let size = fitRect(session.canvasSize, in: CGSize(width: 520, height: 300)).size
        let view = ZStack {
            CanvasContent(layers: session.layers, size: size)
            SwatchMarkers(swatches: session.swatches, layers: session.layers, canvas: size, selectedID: nil, scale: 1)
        }
        .frame(width: size.width, height: size.height)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        return renderer.uiImage
    }

    private static func drawSwatch(_ swatch: Swatch, number: Int, result: Mixing.Result?, at y: CGFloat) {
        let chip = CGRect(x: margin, y: y, width: 64, height: 64)
        UIColor(red: CGFloat(swatch.red) / 255, green: CGFloat(swatch.green) / 255, blue: CGFloat(swatch.blue) / 255, alpha: 1).setFill()
        UIBezierPath(roundedRect: chip, cornerRadius: 6).fill()
        UIColor.lightGray.setStroke()
        UIBezierPath(roundedRect: chip, cornerRadius: 6).stroke()
        let label: UIColor = swatch.value > 60 ? .black : .white
        _ = text("\(number)", at: CGPoint(x: chip.minX + 6, y: chip.minY + 4), font: .boldSystemFont(ofSize: 14), color: label)

        let x = chip.maxX + 14, width = page.width - margin - x
        var line = text("\(number).  \(swatch.hex)   RGB \(swatch.red), \(swatch.green), \(swatch.blue)   value \(Int(swatch.value.rounded()))   "
                        + SwatchDetails.temperature((swatch.red, swatch.green, swatch.blue)),
                        at: CGPoint(x: x, y: y), width: width, font: .boldSystemFont(ofSize: 11))
        let best = result?.pairs.first, single = result?.singles.first
        if let best { line = text("Two paints:  " + recipeText(best), at: CGPoint(x: x, y: line + 3), width: width, font: .systemFont(ofSize: 10)) }
        if let single { line = text("One paint:  " + recipeText(single), at: CGPoint(x: x, y: line + 2), width: width, font: .systemFont(ofSize: 10)) }
        if best == nil && single == nil {
            _ = text("No mix: nothing to mix from.", at: CGPoint(x: x, y: line + 3), width: width, font: .systemFont(ofSize: 10), color: .darkGray)
        }
    }

    private static func recipeText(_ r: Mixing.Recipe) -> String {
        r.parts.map { "\(Mixing.percent($0.share)) \($0.paint.name)" }.joined(separator: " + ")
            + String(format: "   (ΔE %.1f, %@)", r.deltaE, Mixing.closeness(r.deltaE))
    }

    /// Draws text and returns the y below it.
    @discardableResult
    private static func text(_ string: String, at point: CGPoint, width: CGFloat = 532, font: UIFont,
                             color: UIColor = .black) -> CGFloat {
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: color]
        let s = NSAttributedString(string: string, attributes: attributes)
        let bounds = s.boundingRect(with: CGSize(width: width, height: .greatestFiniteMagnitude),
                                    options: [.usesLineFragmentOrigin, .usesFontLeading], context: nil)
        s.draw(with: CGRect(x: point.x, y: point.y, width: width, height: ceil(bounds.height)),
               options: [.usesLineFragmentOrigin, .usesFontLeading], context: nil)
        return point.y + ceil(bounds.height)
    }
}
