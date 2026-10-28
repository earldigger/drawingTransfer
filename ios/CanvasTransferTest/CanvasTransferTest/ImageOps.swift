import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit
import Vision

/// Pixel work, the Swift side of canvastransfer/image_ops.py.
enum ImageOps {
    /// Values stay in the photo's own (sRGB) numbers, so levels act like the prototype's.
    static let context = CIContext(options: [.workingColorSpace: NSNull()])
    static let maxEdge: CGFloat = 3000  // plenty for a canvas, and keeps memory down

    /// Upright pixels at scale 1 (so points are pixels), no larger than `maxEdge`.
    static func prepared(_ image: UIImage) -> UIImage {
        let s = min(1, maxEdge / max(image.size.width, image.size.height))
        let size = CGSize(width: (image.size.width * s).rounded(), height: (image.size.height * s).rounded())
        if image.imageOrientation == .up && s == 1 && image.scale == 1 { return image }
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }

    /// Warp the four corners onto a rectangle.
    static func perspectiveCorrect(_ image: UIImage, corners: Corners) -> UIImage {
        guard let cg = image.cgImage, corners.points.count == 4 else { return image }
        let height = CGFloat(cg.height)
        func flipped(_ p: CGPoint) -> CGPoint { CGPoint(x: p.x, y: height - p.y) }  // Core Image counts from the bottom
        let filter = CIFilter.perspectiveCorrection()
        filter.inputImage = CIImage(cgImage: cg)
        filter.topLeft = flipped(corners.points[0])
        filter.topRight = flipped(corners.points[1])
        filter.bottomRight = flipped(corners.points[2])
        filter.bottomLeft = flipped(corners.points[3])
        guard let output = filter.outputImage,
              let result = context.createCGImage(output, from: output.extent) else { return image }
        return UIImage(cgImage: result)
    }

    /// Dark and light points (0...1) that stretch the image to the full range,
    /// ignoring the darkest and lightest 0.5 % (specks, glare). Turns gray paper
    /// white and pencil lines dark. Same rule as auto_levels in the prototype.
    static func autoLevels(_ image: UIImage) -> (black: CGFloat, white: CGFloat) {
        guard let cg = image.cgImage else { return (0, 1) }
        let w = 256, h = max(1, Int(256 * CGFloat(cg.height) / CGFloat(max(cg.width, 1))))
        var pixels = [UInt8](repeating: 0, count: w * h * 4)
        let drawn = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let ctx = CGContext(data: buffer.baseAddress, width: w, height: h, bitsPerComponent: 8,
                                      bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        guard drawn else { return (0, 1) }

        var histogram = [Int](repeating: 0, count: 256)
        var count = 0
        for i in stride(from: 0, to: pixels.count, by: 4) where pixels[i + 3] > 0 {
            let luma = (299 * Int(pixels[i]) + 587 * Int(pixels[i + 1]) + 114 * Int(pixels[i + 2])) / 1000
            histogram[luma] += 1
            count += 1
        }
        guard count > 0 else { return (0, 1) }
        let clip = count / 200
        var black = 0, white = 255, seen = 0
        while black < 255 && seen + histogram[black] <= clip { seen += histogram[black]; black += 1 }
        seen = 0
        while white > 0 && seen + histogram[white] <= clip { seen += histogram[white]; white -= 1 }
        if white - black < 32 { return (0, 1) }  // nearly flat: don't stretch noise
        return (CGFloat(black) / 255, CGFloat(white) / 255)
    }

    /// Photoshop-style input levels: `black` to 0, `white` to 1.
    static func applyLevels(_ image: UIImage, black: CGFloat, white: CGFloat) -> UIImage {
        guard let cg = image.cgImage, white > black, black > 0 || white < 1 else { return image }
        let s = 1 / (white - black)
        let matrix = CIFilter.colorMatrix()
        matrix.inputImage = CIImage(cgImage: cg)
        matrix.rVector = CIVector(x: s, y: 0, z: 0, w: 0)
        matrix.gVector = CIVector(x: 0, y: s, z: 0, w: 0)
        matrix.bVector = CIVector(x: 0, y: 0, z: s, w: 0)
        matrix.aVector = CIVector(x: 0, y: 0, z: 0, w: 1)
        matrix.biasVector = CIVector(x: -black * s, y: -black * s, z: -black * s, w: 0)
        let clamp = CIFilter.colorClamp()
        clamp.inputImage = matrix.outputImage
        clamp.minComponents = CIVector(x: 0, y: 0, z: 0, w: 0)
        clamp.maxComponents = CIVector(x: 1, y: 1, z: 1, w: 1)
        guard let output = clamp.outputImage,
              let result = context.createCGImage(output, from: output.extent) else { return image }
        return UIImage(cgImage: result)
    }

    /// The rectangle request used for both the live view and the still photo.
    static func rectangleRequest() -> VNDetectRectanglesRequest {
        let request = VNDetectRectanglesRequest()
        request.minimumAspectRatio = 0.3  // short side / long side
        request.maximumAspectRatio = 1.0
        request.minimumSize = 0.2  // of the frame
        request.quadratureTolerance = 30  // degrees off square at the corners: photos are taken at an angle
        request.minimumConfidence = 0.5
        request.maximumObservations = 1
        return request
    }

    /// The most likely rectangle in an upright photo, as pixel corners.
    static func detectRectangle(in image: UIImage) -> Corners? {
        guard let cg = image.cgImage else { return nil }
        let request = rectangleRequest()
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
        guard let r = request.results?.first else { return nil }
        let w = CGFloat(cg.width), h = CGFloat(cg.height)
        func pixel(_ p: CGPoint) -> CGPoint { CGPoint(x: p.x * w, y: (1 - p.y) * h) }  // Vision counts from the bottom
        return Corners(points: [pixel(r.topLeft), pixel(r.topRight), pixel(r.bottomRight), pixel(r.bottomLeft)])
    }

    /// The finished layer image: corrected, then auto levels.
    static func layerImage(from photo: UIImage, corners: Corners) -> UIImage {
        let corrected = perspectiveCorrect(photo, corners: corners)
        let levels = autoLevels(corrected)
        return applyLevels(corrected, black: levels.black, white: levels.white)
    }
}
