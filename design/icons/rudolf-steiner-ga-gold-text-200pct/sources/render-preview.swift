import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Flatten a preview of native foreground exports over the existing linen.
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let background = URL(fileURLWithPath: CommandLine.arguments[2])
func read(_ url: URL) -> CGImage {
    let source = CGImageSourceCreateWithURL(url as CFURL, nil)!
    return CGImageSourceCreateImageAtIndex(source, 0, nil)!
}
let rect = CGRect(x: 0, y: 0, width: 1024, height: 1024)
let space = CGColorSpace(name: CGColorSpace.sRGB)!
let canvas = CGContext(data: nil, width: 1024, height: 1024, bitsPerComponent: 8,
                       bytesPerRow: 4096, space: space,
                       bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
canvas.draw(read(background), in: rect)
canvas.draw(read(root.appendingPathComponent("rudolf-steiner-ga-gold-200pct.png")), in: rect)
let destination = CGImageDestinationCreateWithURL(root.appendingPathComponent("preview-on-linen.png") as CFURL,
                                                UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(destination, canvas.makeImage()!, nil)
precondition(CGImageDestinationFinalize(destination))
print("Wrote flattened comparison preview.")
