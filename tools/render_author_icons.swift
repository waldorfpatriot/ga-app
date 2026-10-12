import AppKit
import CoreText

// Install the editable layered literary icons first, with flattened artwork
// and the original linen-and-gold lettering retained as fallbacks.
let manifestURL = URL(fileURLWithPath: CommandLine.arguments[1])
let root = URL(fileURLWithPath: CommandLine.arguments[2])
let data = try Data(contentsOf: manifestURL)
let manifest = try JSONSerialization.jsonObject(with: data) as! [String: Any]
let authors = manifest["authors"] as! [[String: Any]]
let fontURL = root.appendingPathComponent("apple/AuthorReader/CoverFonts/crimson-pro-regular.ttf")
CTFontManagerRegisterFontsForURL(fontURL as CFURL, .process, nil)
let baseIcon = root.appendingPathComponent("apple/GA/ga.icon")
let original = try JSONSerialization.jsonObject(with: Data(contentsOf: baseIcon.appendingPathComponent("icon.json"))) as! [String: Any]
for author in authors {
    let directory = root.appendingPathComponent("editions/\(author["slug"] as! String)/apple/author.icon")
    let assets = directory.appendingPathComponent("Assets")
    try FileManager.default.createDirectory(at: assets, withIntermediateDirectories: true)
    let slug = author["slug"] as! String
    let layered = root.appendingPathComponent("design/icons/literary-emblems-v2/icon-composer/documents/\(slug).icon")
    let layeredJSON = layered.appendingPathComponent("icon.json")
    if FileManager.default.fileExists(atPath: layeredJSON.path) {
        let encoded = try Data(contentsOf: layeredJSON)
        let icon = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
        for group in icon["groups"] as! [[String: Any]] {
            for layer in group["layers"] as! [[String: Any]] {
                let filename = layer["image-name"] as! String
                // Missing layer data is an error, rather than reverting an
                // existing edition to different artwork during regeneration.
                let pixels = try Data(contentsOf: layered.appendingPathComponent("Assets/\(filename)"))
                try pixels.write(to: assets.appendingPathComponent(filename), options: .atomic)
            }
        }
        try encoded.write(to: directory.appendingPathComponent("icon.json"), options: .atomic)
        continue
    }
    let artwork = root.appendingPathComponent("design/icons/literary-emblems-v2/exports/\(slug).png")
    if FileManager.default.fileExists(atPath: artwork.path) {
        let destination = assets.appendingPathComponent("literary-emblem-v2.png")
        try Data(contentsOf: artwork).write(to: destination, options: .atomic)
        // The artwork already includes its background and satin-gold finish.
        // An opaque, non-glass layer preserves its contrast at small sizes.
        let icon: [String: Any] = [
            "fill": ["solid": "extended-srgb:0.12549,0.23922,0.21176,1.00000"],
            "groups": [[
                "name": "Literary emblem",
                "layers": [[
                    "image-name": "literary-emblem-v2.png",
                    "name": "\(author["author_short_name"] as! String) literary emblem",
                    "glass": false,
                    "opacity": 1,
                    "position": ["scale": 1, "translation-in-points": [0, 0]]
                ]],
                "shadow": ["kind": "none", "opacity": 0],
                "translucency": ["enabled": false, "value": 0]
            ]],
            "supported-platforms": ["squares": "shared"]
        ]
        let encoded = try JSONSerialization.data(withJSONObject: icon, options: [.prettyPrinted, .sortedKeys])
        try encoded.write(to: directory.appendingPathComponent("icon.json"), options: .atomic)
        continue
    }
    let background = assets.appendingPathComponent("linen.png")
    if FileManager.default.fileExists(atPath: background.path) { try FileManager.default.removeItem(at: background) }
    try FileManager.default.copyItem(at: baseIcon.appendingPathComponent("Assets/01-linen-background 2.png"), to: background)
    let image = NSImage(size: NSSize(width: 1024, height: 1024))
    image.lockFocus()
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.45)
    shadow.shadowOffset = NSSize(width: 1, height: -3)
    shadow.shadowBlurRadius = 3
    let name = author["author_name"] as! String
    let short = author["author_short_name"] as! String
    let words = name.components(separatedBy: " ")
    let lines: String
    if name.count > 24 { lines = short.uppercased() }
    else if words.count >= 2 { lines = words.dropLast().joined(separator: " ").uppercased() + "\n" + words.last!.uppercased() }
    else { lines = name.uppercased() }
    var size: CGFloat = 120
    var attributes: [NSAttributedString.Key: Any] = [:]
    repeat {
        attributes = [.font: NSFont(name: "CrimsonPro-Regular", size: size) ?? NSFont.systemFont(ofSize: size), .foregroundColor: NSColor(red: 0.84, green: 0.69, blue: 0.39, alpha: 1), .paragraphStyle: paragraph, .shadow: shadow, .kern: 2]
        if (lines as NSString).size(withAttributes: attributes).width <= 840 { break }
        size -= 2
    } while size > 50
    (lines as NSString).draw(in: NSRect(x: 78, y: 285, width: 868, height: 430), withAttributes: attributes)
    attributes[.font] = NSFont(name: "CrimsonPro-Regular", size: 85) ?? NSFont.systemFont(ofSize: 85)
    attributes[.kern] = 8
    ("WERKE" as NSString).draw(in: NSRect(x: 80, y: 170, width: 864, height: 100), withAttributes: attributes)
    image.unlockFocus()
    let png = NSBitmapImageRep(data: image.tiffRepresentation!)!.representation(using: .png, properties: [:])!
    try png.write(to: assets.appendingPathComponent("author-gold.png"))
    var icon = original
    var groups = original["groups"] as! [[String: Any]]
    groups[0]["layers"] = [["image-name": "author-gold.png", "name": "Author gold lettering", "position": ["scale": 1, "translation-in-points": [0, 0]]]]
    groups[2]["layers"] = [["image-name": "linen.png", "name": "Original linen background"]]
    icon["groups"] = groups
    let encoded = try JSONSerialization.data(withJSONObject: icon, options: [.prettyPrinted, .sortedKeys])
    try encoded.write(to: directory.appendingPathComponent("icon.json"))
}
print("Generated \(authors.count) author Icon Composer variants.")
