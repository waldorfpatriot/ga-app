import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Raster export of the native lettering masks with a shared foil material.
// The source photograph and ImageGen originals are never changed.
let package = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "design/icons/rudolf-steiner-ga-original-materials", isDirectory: true)
let size = 1024
let rect = CGRect(x: 0, y: 0, width: size, height: size)
let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!

func read(_ relative: String) -> CGImage {
    let url = package.appendingPathComponent(relative)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        fatalError("Cannot read \(relative)")
    }
    precondition(image.width == size && image.height == size, "Non-1024 asset: \(relative)")
    return image
}

func context() -> CGContext {
    CGContext(data: nil, width: size, height: size, bitsPerComponent: 8,
              bytesPerRow: size * 4, space: colorSpace,
              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
}

func save(_ image: CGImage, _ relative: String) {
    let url = package.appendingPathComponent(relative)
    let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(destination, image, nil)
    precondition(CGImageDestinationFinalize(destination), "Cannot save \(relative)")
}

let gold = read("materials/gold-stamping.png")
var layers: [CGImage] = []
for stem in ["02-rudolf", "03-steiner", "04-ga"] {
    let mask = read("masks/\(stem)-mask.png")
    let canvas = context()
    canvas.draw(gold, in: rect)
    canvas.setBlendMode(.destinationIn)
    canvas.draw(mask, in: rect)
    let layer = canvas.makeImage()!
    save(layer, "\(stem)-gold.png")
    layers.append(layer)
}

let combined = context()
for image in layers { combined.draw(image, in: rect) }
save(combined.makeImage()!, "alternatives/02-lettering-combined-gold.png")

let preview = context()
preview.draw(read("01-linen-background.png"), in: rect)
for image in layers { preview.draw(image, in: rect) }
save(preview.makeImage()!, "preview.png")
print("Exported 3 foil lettering layers, combined alternative and preview; all 1024 × 1024 sRGB.")
