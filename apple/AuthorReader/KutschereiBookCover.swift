import CoreText
import SwiftUI
#if os(macOS)
import AppKit
private typealias CoverPlatformImage = NSImage
#else
import UIKit
private typealias CoverPlatformImage = UIImage
#endif

/// The cloth-and-gold cover from Kutscherei's Falz app. The unchanged source and
/// its original materials are preserved in vendor/kutscherei-covers.
struct KutschereiBookCover: View {
    let title: String
    let gaLabel: String

    var body: some View {
        let materials = KutschereiCoverMaterials.shared
        let category = materials.category(for: gaLabel)
        GeometryReader { geometry in
            let width = geometry.size.width
            ZStack {
                CoverTextileSurface(color: category.color, textureURL: materials.textureURL(for: category))
                Rectangle().fill(LinearGradient(stops: [
                    .init(color: .black.opacity(0.35), location: 0),
                    .init(color: .white.opacity(0.13), location: 0.3),
                    .init(color: .black.opacity(0.14), location: 0.7),
                    .init(color: .clear, location: 1)
                ], startPoint: .leading, endPoint: .trailing))
                    .frame(width: 10).frame(maxWidth: .infinity, alignment: .leading)
                VStack(spacing: 0) {
                    CoverGoldText(text: AppEdition.authorName.uppercased(), font: CoverTypography.ui(width * 0.049, weight: .medium), textureURL: materials.goldURL)
                        .tracking(1.2).lineLimit(2).minimumScaleFactor(0.6)
                        .multilineTextAlignment(.center).padding(.horizontal, width * 0.08)
                        .padding(.top, width * 0.20)
                    Rectangle().fill(CoverTypography.gold.opacity(0.63))
                        .frame(width: width * 0.38, height: 0.65).padding(.top, width * 0.08)
                    Spacer(minLength: 12)
                    CoverGoldText(text: title, font: CoverTypography.serif(width * 0.113), textureURL: materials.goldURL)
                        .multilineTextAlignment(.center).lineLimit(6).minimumScaleFactor(0.58)
                        .padding(.horizontal, width * 0.13)
                    Spacer(minLength: 12)
                    CoverGoldText(text: gaLabel.uppercased(), font: CoverTypography.ui(width * 0.061, weight: .medium), textureURL: materials.goldURL)
                        .tracking(1.8)
                    Text(AppEdition.editionTitle.uppercased()).font(CoverTypography.ui(width * 0.037))
                        .lineLimit(2).minimumScaleFactor(0.6).multilineTextAlignment(.center)
                        .padding(.horizontal, width * 0.08)
                        .tracking(1.5).foregroundStyle(CoverTypography.gold.opacity(0.83))
                        .padding(.top, 9).padding(.bottom, width * 0.14)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 2.5))
            .overlay(RoundedRectangle(cornerRadius: 2.5).stroke(.black.opacity(0.14), lineWidth: 0.8))
            .overlay(alignment: .trailing) {
                Rectangle().fill(.white.opacity(0.09)).frame(width: 1).padding(.vertical, 3)
            }
        }
        .aspectRatio(0.71, contentMode: .fit)
        .accessibilityHidden(true)
    }
}

private enum CoverTypography {
    static let gold = Color(coverHex: "D9B874")
    // Cover lettering is artwork. Accessible titles outside the cover continue
    // to follow Dynamic Type without changing these proportions.
    static func serif(_ size: CGFloat) -> Font { .custom("CrimsonPro-Regular", fixedSize: size) }
    static func ui(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom("DMSans-Regular", fixedSize: size).weight(weight)
    }
}

private struct CoverCategory: Decodable {
    let id: String
    let colorHex: String
    let gaRanges: [String]
    let texturePath: String?

    static let neutral = CoverCategory(id: "neutral", colorHex: "#6E6650", gaRanges: [], texturePath: nil)
    var color: Color { Color(coverHex: colorHex) }

    func contains(_ label: String) -> Bool {
        guard let volume = CoverVolumeNumber(label) else { return false }
        return gaRanges.contains { range in
            let bounds = range.replacingOccurrences(of: "–", with: "-")
                .replacingOccurrences(of: "—", with: "-").split(separator: "-", maxSplits: 1)
            guard let first = bounds.first, let lower = CoverVolumeNumber(String(first)) else { return false }
            let upper = bounds.count == 2 ? CoverVolumeNumber(String(bounds[1]), family: lower.family) : lower
            guard let upper, upper.number >= lower.number, volume.family == lower.family else { return false }
            return (lower.number...upper.number).contains(volume.number)
        }
    }
}

private struct CoverVolumeNumber {
    enum Family { case ga, artistic }
    let number: Int
    let family: Family

    init?(_ label: String, family defaultFamily: Family = .ga) {
        var value = label.uppercased().filter { !$0.isWhitespace }
        if value.hasPrefix("EGA") { value.removeFirst(3); family = .ga }
        else if value.hasPrefix("GA") { value.removeFirst(2); family = .ga }
        else if value.hasPrefix("K") { value.removeFirst(); family = .artistic }
        else { family = defaultFamily }
        guard let number = Int(value.prefix(while: \.isNumber)) else { return nil }
        self.number = number
    }
}

@MainActor
private final class KutschereiCoverMaterials {
    static let shared = KutschereiCoverMaterials()
    private let categories: [CoverCategory]
    private let rootURL: URL?

    private init() {
        let bundle = Bundle.main
        for name in ["crimson-pro-regular", "crimson-pro-semibold", "dm-sans-regular", "dm-sans-semibold"] {
            if let url = bundle.url(forResource: name, withExtension: "ttf", subdirectory: "CoverFonts") {
                CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
            }
        }
        let url = bundle.url(forResource: "categories", withExtension: "json", subdirectory: "CoverMaterials")
        rootURL = url?.deletingLastPathComponent()
        struct Manifest: Decodable { let categories: [CoverCategory] }
        if let url, let data = try? Data(contentsOf: url), let manifest = try? JSONDecoder().decode(Manifest.self, from: data) {
            categories = manifest.categories
        } else {
            categories = []
        }
    }

    func category(for label: String) -> CoverCategory {
        guard AppEdition.isSteiner else { return .neutral }
        return categories.first { $0.contains(label) } ?? .neutral
    }

    func textureURL(for category: CoverCategory) -> URL? {
        category.texturePath.flatMap { rootURL?.appendingPathComponent($0) }
    }

    var goldURL: URL? { rootURL?.appendingPathComponent("gold/gold-foil.png") }
}

private struct CoverTextileSurface: View {
    let color: Color
    let textureURL: URL?
    var body: some View {
        ZStack {
            color
            if let textureURL, let image = CoverTextureImages.shared.image(textureURL) {
                Image(coverPlatformImage: image).resizable(resizingMode: .tile).interpolation(.high)
            }
            LinearGradient(colors: [.white.opacity(0.12), .clear, .black.opacity(0.19)], startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }
}

@MainActor
private final class CoverTextureImages {
    static let shared = CoverTextureImages()
    private let cache = NSCache<NSURL, CoverPlatformImage>()
    func image(_ url: URL) -> CoverPlatformImage? {
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

private struct CoverGoldText: View {
    let text: String
    let font: Font
    let textureURL: URL?
    var body: some View {
        Text(text).font(font).foregroundStyle(letteringStyle)
            .shadow(color: .black.opacity(0.68), radius: 0.4, x: 0, y: 0.8)
            .shadow(color: .white.opacity(0.15), radius: 0.3, x: 0, y: -0.6)
    }

    private var letteringStyle: AnyShapeStyle {
        if let textureURL, let image = CoverTextureImages.shared.image(textureURL) {
            // Paint the laid-out glyphs directly so wrapping and scaling cannot
            // diverge between a solid text layer and a separate texture mask.
            return AnyShapeStyle(ImagePaint(image: Image(coverPlatformImage: image)))
        }
        return AnyShapeStyle(CoverTypography.gold)
    }
}

private extension Color {
    init(coverHex: String) {
        let clean = coverHex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        let value = UInt64(clean, radix: 16) ?? 0x69604B
        self.init(.sRGB, red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255, opacity: 1)
    }
}

private extension Image {
    init(coverPlatformImage: CoverPlatformImage) {
        #if os(macOS)
        self.init(nsImage: coverPlatformImage)
        #else
        self.init(uiImage: coverPlatformImage)
        #endif
    }
}
