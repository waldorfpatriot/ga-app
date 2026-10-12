#!/usr/bin/env swift

import AppKit
import Foundation

struct Category: Decodable {
    let id: String
    let texturePath: String
    let goldTexturePath: String
}

struct Manifest: Decodable {
    let tileSize: Int
    let categories: [Category]
    let gold: Gold
}

struct Gold: Decodable {
    let texturePath: String
}

let scriptURL = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
let rootURL = scriptURL.deletingLastPathComponent()
let manifest = try JSONDecoder().decode(
    Manifest.self,
    from: Data(contentsOf: rootURL.appendingPathComponent("categories.json"))
)

let paths = manifest.categories.flatMap { [$0.texturePath, $0.goldTexturePath] } + [manifest.gold.texturePath]
var failures: [String] = []

func rgb(_ bitmap: NSBitmapImageRep, _ x: Int, _ y: Int) -> (Double, Double, Double) {
    let c = bitmap.colorAt(x: x, y: y)!.usingColorSpace(.sRGB)!
    return (c.redComponent * 255, c.greenComponent * 255, c.blueComponent * 255)
}

func delta(_ a: (Double, Double, Double), _ b: (Double, Double, Double)) -> Double {
    (abs(a.0 - b.0) + abs(a.1 - b.1) + abs(a.2 - b.2)) / 3
}

for path in paths {
    let url = rootURL.appendingPathComponent(path)
    guard let bitmap = NSBitmapImageRep(data: try Data(contentsOf: url)) else {
        failures.append("cannot decode \(path)")
        continue
    }
    if bitmap.pixelsWide != manifest.tileSize || bitmap.pixelsHigh != manifest.tileSize {
        failures.append("wrong dimensions: \(path)")
        continue
    }

    var edge = 0.0
    var edgeCount = 0.0
    var interior = 0.0
    var interiorCount = 0.0
    let last = manifest.tileSize - 1
    for i in 0..<manifest.tileSize {
        edge += delta(rgb(bitmap, last, i), rgb(bitmap, 0, i))
        edge += delta(rgb(bitmap, i, last), rgb(bitmap, i, 0))
        edgeCount += 2
    }
    for y in stride(from: 0, to: manifest.tileSize, by: 8) {
        for x in stride(from: 0, to: last, by: 8) {
            interior += delta(rgb(bitmap, x, y), rgb(bitmap, x + 1, y))
            interior += delta(rgb(bitmap, y, x), rgb(bitmap, y, x + 1))
            interiorCount += 2
        }
    }
    let edgeMean = edge / edgeCount
    let interiorMean = interior / interiorCount
    let ratio = edgeMean / max(interiorMean, 0.001)
    if ratio > 1.75 {
        failures.append(String(format: "visible seam risk %@ ratio %.2f", path, ratio))
    }
    print(String(format: "%-42@ 512x512 seam %.2f / interior %.2f (%.2fx)", path as NSString, edgeMean, interiorMean, ratio))
}

if failures.isEmpty {
    print("PASS: \(paths.count) texture files decode, match dimensions, and pass seam statistics.")
} else {
    for failure in failures { fputs("FAIL: \(failure)\n", stderr) }
    exit(1)
}
