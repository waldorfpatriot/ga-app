#if os(macOS)
import AppKit
private typealias PlatformImage = NSImage
#else
import UIKit
private typealias PlatformImage = UIImage
#endif
import FalzCore
import SwiftUI

enum FalzTheme {
    static let paper = Color(hex: "FCF8EC")
    static let background = Color(hex: "F2EEE3")
    static let sidebar = Color(hex: "EAE6DC")
    static let ink = Color(hex: "292B24")
    static let muted = Color(hex: "7F7C70")
    static let line = Color(hex: "D7D1C2")
    static let gold = Color(hex: "D9B874")
    static func serif(_ size: CGFloat) -> Font { .custom("CrimsonPro-Regular", size: size) }
    static func ui(_ size: CGFloat, weight: Font.Weight = .regular) -> Font { .custom("DMSans-Regular", size: size).weight(weight) }
}

/// The same letterpress initials and gold rule used by the bundled app icon.
struct GALogo: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("GA").font(.custom("CrimsonPro-SemiBold", size: 52)).tracking(-2)
                .foregroundStyle(FalzTheme.ink)
            Rectangle().fill(FalzTheme.gold).frame(width: 72, height: 1.5)
            Text("GESAMTAUSGABE").font(FalzTheme.ui(9, weight: .medium)).tracking(2)
                .foregroundStyle(FalzTheme.muted)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("GA · Gesamtausgabe")
    }
}

extension Color {
    init(hex: String) {
        let clean = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        let value = UInt64(clean, radix: 16) ?? 0x69604B
        self.init(.sRGB, red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255, opacity: 1)
    }
}

struct TextileSurface: View {
    let color: Color
    let textureURL: URL?
    var body: some View {
        ZStack {
            color
            if let textureURL, let image = TextureImages.shared.image(textureURL) {
                Image(platformImage: image).resizable(resizingMode: .tile).interpolation(.high)
            }
            LinearGradient(colors: [.white.opacity(0.12), .clear, .black.opacity(0.19)], startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }
}

@MainActor
final class TextureImages {
    static let shared = TextureImages()
    private let cache = NSCache<NSURL, PlatformImage>()
    fileprivate func image(_ url: URL) -> PlatformImage? {
        if let found = cache.object(forKey: url as NSURL) { return found }
        #if os(macOS)
        guard let image = NSImage(contentsOf: url) else { return nil }
        image.size = NSSize(width: 180, height: 180)
        #else
        guard let source = UIImage(contentsOfFile: url.path) else { return nil }
        let image = UIGraphicsImageRenderer(size: CGSize(width: 180, height: 180)).image { _ in
            source.draw(in: CGRect(x: 0, y: 0, width: 180, height: 180))
        }
        #endif
        cache.setObject(image, forKey: url as NSURL)
        return image
    }
}

struct GoldText: View {
    let text: String
    let font: Font
    let textureURL: URL?
    var body: some View {
        Text(text).font(font).foregroundStyle(FalzTheme.gold)
            .overlay {
                if let textureURL, let image = TextureImages.shared.image(textureURL) {
                    Image(platformImage: image).resizable(resizingMode: .tile)
                        .mask { Text(text).font(font) }
                }
            }
            .shadow(color: .black.opacity(0.68), radius: 0.4, x: 0, y: 0.8)
            .shadow(color: .white.opacity(0.15), radius: 0.3, x: 0, y: -0.6)
    }
}

private extension Image {
    init(platformImage: PlatformImage) {
        #if os(macOS)
        self.init(nsImage: platformImage)
        #else
        self.init(uiImage: platformImage)
        #endif
    }
}
