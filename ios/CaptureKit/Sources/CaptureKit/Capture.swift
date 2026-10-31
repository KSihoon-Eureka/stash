import Foundation

/// What the share extension sends to the Mac receiver (`POST /capture`).
public struct Capture: Codable, Equatable, Sendable {
    public var url: String?
    public var text: String?
    public var title: String?
    public var sourceApp: String?
    public var capturedAt: String

    public init(url: String? = nil, text: String? = nil, title: String? = nil,
                sourceApp: String? = nil, capturedAt: Date = Date()) {
        self.url = url
        self.text = text
        self.title = title
        self.sourceApp = sourceApp
        self.capturedAt = ISO8601DateFormatter().string(from: capturedAt)
    }

    public var isEmpty: Bool { (url ?? "").isEmpty && (text ?? "").isEmpty }

    enum CodingKeys: String, CodingKey {
        case url, text, title
        case sourceApp = "source_app"
        case capturedAt = "captured_at"
    }
}

/// Server address + token, shared between the app and the extension via the App Group.
public struct ReceiverConfig: Equatable, Sendable {
    public static let appGroup = "group.com.sihoonkim.stash"

    public var serverURL: String
    public var token: String

    public init(serverURL: String, token: String) {
        self.serverURL = serverURL
        self.token = token
    }

    public var isComplete: Bool { baseURL != nil && !token.isEmpty }

    /// Accepts "100.101.1.2:8765" or "http://mac.local:8765/" and normalizes it.
    public var baseURL: URL? {
        var raw = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if raw.isEmpty { return nil }
        if !raw.contains("://") { raw = "http://" + raw }
        while raw.hasSuffix("/") { raw.removeLast() }
        guard let url = URL(string: raw), url.host != nil else { return nil }
        return url
    }

    /// Keys must match the app's @AppStorage("serverURL") / @AppStorage("token").
    public static func load(_ defaults: UserDefaults? = UserDefaults(suiteName: appGroup)) -> ReceiverConfig {
        ReceiverConfig(serverURL: defaults?.string(forKey: "serverURL") ?? "",
                       token: defaults?.string(forKey: "token") ?? "")
    }
}
