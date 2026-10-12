#!/usr/bin/env swift

import AppKit
import Foundation

struct Category: Decodable {
    let id: String
    let name: String
    let shortName: String
    let colorHex: String
    let texturePath: String
    let goldTexturePath: String
}

struct Manifest: Decodable {
    let tileSize: Int
    let categories: [Category]
}

let scriptURL = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
let rootURL = scriptURL.deletingLastPathComponent()
let manifestURL = rootURL.appendingPathComponent("categories.json")
let manifest = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: manifestURL))

func hexRGB(_ hex: String) -> (Double, Double, Double) {
    let value = UInt64(hex.dropFirst(), radix: 16)!
    return (
        Double((value >> 16) & 0xff),
        Double((value >> 8) & 0xff),
        Double(value & 0xff)
    )
}

func stableSeed(_ string: String) -> UInt32 {
    string.utf8.reduce(UInt32(2166136261)) { ($0 ^ UInt32($1)) &* 16777619 }
}

func hashNoise(_ x: Int, _ y: Int, _ seed: UInt32) -> Double {
    var v = UInt32(truncatingIfNeeded: x &* 374_761_393)
    v &+= UInt32(truncatingIfNeeded: y &* 668_265_263)
    v ^= seed
    v = (v ^ (v >> 13)) &* 1_274_126_177
    return Double(v ^ (v >> 16)) / Double(UInt32.max) * 2.0 - 1.0
}

@inline(__always) func clampByte(_ value: Double) -> UInt8 {
    UInt8(max(0, min(255, value.rounded())))
}

func makeBitmap(size: Int, pixel: (Int, Int) -> (UInt8, UInt8, UInt8, UInt8)) -> NSBitmapImageRep {
    let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: size,
        pixelsHigh: size,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: size * 4,
        bitsPerPixel: 32
    )!
    let bytes = bitmap.bitmapData!
    for y in 0..<size {
        for x in 0..<size {
            let (r, g, b, a) = pixel(x, y)
            let offset = y * bitmap.bytesPerRow + x * 4
            bytes[offset] = r
            bytes[offset + 1] = g
            bytes[offset + 2] = b
            bytes[offset + 3] = a
        }
    }
    return bitmap
}

func writePNG(_ bitmap: NSBitmapImageRep, to url: URL) throws {
    let data = bitmap.representation(using: .png, properties: [.compressionFactor: 1.0])!
    try data.write(to: url, options: .atomic)
}

func linenTile(colorHex: String, size: Int, seed: UInt32) -> NSBitmapImageRep {
    let base = hexRGB(colorHex)
    let tau = Double.pi * 2
    return makeBitmap(size: size) { x, y in
        let fx = Double(x)
        let fy = Double(y)

        // Integer frequencies make every component exactly periodic over the tile.
        let warp = sin(tau * fx / 6.0) * 5.6 + sin(tau * fx / 13.0) * 1.8
        let weft = sin(tau * fy / 6.0 + Double(seed % 17) * 0.07) * 4.8
        let twill = sin(tau * (fx + fy) / 24.0) * 1.45
        let broad = sin(tau * fx * 3.0 / Double(size) + 0.4)
            + cos(tau * fy * 5.0 / Double(size) + 1.1)
            + sin(tau * (fx + fy) * 2.0 / Double(size) + 2.4)
        let pore = hashNoise(x, y, seed) * 2.1
        let crossing = sin(tau * fx / 6.0) * sin(tau * fy / 6.0) * 1.7
        let light = warp + weft + twill + broad * 1.2 + pore + crossing
        let chromaNoise = hashNoise((x + 137) % size, (y + 293) % size, seed ^ 0x9e3779b9) * 1.4
        return (
            clampByte(base.0 + light + chromaNoise * 0.45),
            clampByte(base.1 + light + chromaNoise * 0.12),
            clampByte(base.2 + light - chromaNoise * 0.35),
            255
        )
    }
}

func goldTile(size: Int, seed: UInt32, warmth: Double = 0) -> NSBitmapImageRep {
    let tau = Double.pi * 2
    return makeBitmap(size: size) { x, y in
        let fx = Double(x)
        let fy = Double(y)
        let brushing = sin(tau * fx / 17.0) * 7.0
            + sin(tau * fx / 43.0 + 0.7) * 5.0
            + cos(tau * fy * 3.0 / Double(size)) * 2.5
        let foil = hashNoise(x, y, seed) * 7.0
        let flake = pow(max(0, hashNoise((x + 73) % size, (y + 191) % size, seed ^ 0x85ebca6b)), 7.0) * 23.0
        let shade = brushing + foil + flake
        return (
            clampByte(200 + shade + warmth * 7),
            clampByte(166 + shade * 0.78 + warmth * 3),
            clampByte(86 + shade * 0.42 - warmth * 2),
            255
        )
    }
}

let fileManager = FileManager.default
try fileManager.createDirectory(at: rootURL.appendingPathComponent("linen"), withIntermediateDirectories: true)
try fileManager.createDirectory(at: rootURL.appendingPathComponent("gold"), withIntermediateDirectories: true)

for (index, category) in manifest.categories.enumerated() {
    let seed = stableSeed(category.id)
    try writePNG(
        linenTile(colorHex: category.colorHex, size: manifest.tileSize, seed: seed),
        to: rootURL.appendingPathComponent(category.texturePath)
    )
    try writePNG(
        goldTile(size: manifest.tileSize, seed: seed ^ 0xa5a5a5a5, warmth: Double(index % 5 - 2) * 0.12),
        to: rootURL.appendingPathComponent(category.goldTexturePath)
    )
}

try writePNG(
    goldTile(size: manifest.tileSize, seed: 0x474f4c44),
    to: rootURL.appendingPathComponent("gold/gold-foil.png")
)

// Contact sheet: each swatch is tiled four times so seams remain visible during review.
let columns = 2
let cellWidth: CGFloat = 620
let cellHeight: CGFloat = 232
let rows = Int(ceil(Double(manifest.categories.count) / Double(columns)))
let canvasSize = NSSize(width: cellWidth * CGFloat(columns), height: cellHeight * CGFloat(rows))
let canvas = NSImage(size: canvasSize)
canvas.lockFocus()
NSColor(calibratedWhite: 0.075, alpha: 1).setFill()
NSBezierPath(rect: NSRect(origin: .zero, size: canvasSize)).fill()

for (index, category) in manifest.categories.enumerated() {
    let column = index % columns
    let row = index / columns
    let originX = CGFloat(column) * cellWidth
    let originY = canvasSize.height - CGFloat(row + 1) * cellHeight
    let inset = NSRect(x: originX + 18, y: originY + 18, width: cellWidth - 36, height: cellHeight - 36)

    if let texture = NSImage(contentsOf: rootURL.appendingPathComponent(category.texturePath)) {
        let tileSide: CGFloat = 98
        for ty in 0..<2 {
            for tx in 0..<6 {
                texture.draw(
                    in: NSRect(x: inset.minX + CGFloat(tx) * tileSide, y: inset.minY + CGFloat(ty) * tileSide, width: tileSide, height: tileSide),
                    from: NSRect(origin: .zero, size: texture.size),
                    operation: .sourceOver,
                    fraction: 1
                )
            }
        }
    }

    let overlay = NSRect(x: inset.minX, y: inset.maxY - 58, width: inset.width, height: 58)
    NSColor(calibratedWhite: 0.03, alpha: 0.66).setFill()
    NSBezierPath(rect: overlay).fill()
    let title = "\(category.shortName)  \(category.colorHex)"
    title.draw(
        at: NSPoint(x: overlay.minX + 14, y: overlay.minY + 18),
        withAttributes: [
            .font: NSFont.systemFont(ofSize: 19, weight: .semibold),
            .foregroundColor: NSColor.white
        ]
    )

    if let gold = NSImage(contentsOf: rootURL.appendingPathComponent(category.goldTexturePath)) {
        gold.draw(
            in: NSRect(x: inset.maxX - 122, y: inset.minY + 12, width: 104, height: 32),
            from: NSRect(origin: .zero, size: gold.size),
            operation: .sourceOver,
            fraction: 1
        )
    }
}
canvas.unlockFocus()
let contactRep = NSBitmapImageRep(data: canvas.tiffRepresentation!)!
try writePNG(contactRep, to: rootURL.appendingPathComponent("overview.png"))

print("Generated \(manifest.categories.count) linen tiles, \(manifest.categories.count + 1) gold tiles and overview.png")
