import Foundation
import UniformTypeIdentifiers

/// Turns whatever a host app put on the share sheet into a `Capture`.
/// Instagram shares a reel as a `public.url`; many apps share text with a link inside.
public enum ShareItemExtractor {
    public static func capture(from providers: [NSItemProvider], attachedText: String? = nil,
                               sourceApp: String? = nil) async -> Capture {
        var urls: [URL] = []
        var texts: [String] = []
        if let attachedText, !attachedText.isEmpty { texts.append(attachedText) }

        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier),
               let item = try? await provider.loadItem(forTypeIdentifier: UTType.url.identifier) {
                if let url = item as? URL { urls.append(url) }
                else if let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) { urls.append(url) }
                else if let str = item as? String, let url = URL(string: str) { urls.append(url) }
            } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier),
                      let item = try? await provider.loadItem(forTypeIdentifier: UTType.plainText.identifier) {
                if let str = item as? String { texts.append(str) }
                else if let data = item as? Data, let str = String(data: data, encoding: .utf8) { texts.append(str) }
            }
        }
        return make(urls: urls, texts: texts, sourceApp: sourceApp)
    }

    /// Pure merge step: first web URL wins (falling back to one found inside the text).
    public static func make(urls: [URL], texts: [String], sourceApp: String? = nil) -> Capture {
        let text = texts.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
            .joined(separator: "\n\n")
        let url = urls.first { ["http", "https"].contains($0.scheme?.lowercased() ?? "") }
            ?? firstLink(in: text)
        return Capture(url: url?.absoluteString, text: text.isEmpty ? nil : text, sourceApp: sourceApp)
    }

    static func firstLink(in text: String) -> URL? {
        guard let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) else { return nil }
        let range = NSRange(text.startIndex..., in: text)
        return detector.matches(in: text, range: range).compactMap(\.url)
            .first { ["http", "https"].contains($0.scheme?.lowercased() ?? "") }
    }
}
