import Foundation
import Testing
import UniformTypeIdentifiers
@testable import CaptureKit

let reel = "https://www.instagram.com/reel/DAbc123XyZ/?igsh=MWQ1ZGUxMzBkMA=="

@Suite struct ExtractorTests {
    @Test func urlProviderLikeInstagram() async {
        let provider = NSItemProvider(item: URL(string: reel)! as NSURL, typeIdentifier: UTType.url.identifier)
        let capture = await ShareItemExtractor.capture(from: [provider], sourceApp: "com.burbn.instagram")
        #expect(capture.url == reel)
        #expect(capture.sourceApp == "com.burbn.instagram")
    }

    @Test func linkInsidePlainText() async {
        let provider = NSItemProvider(item: "이 영상 꼭 봐 \(reel)" as NSString, typeIdentifier: UTType.plainText.identifier)
        let capture = await ShareItemExtractor.capture(from: [provider])
        #expect(capture.url == reel)
        #expect(capture.text?.contains("꼭 봐") == true)
    }

    @Test func dedupesTextAndIgnoresNonWebURLs() {
        let capture = ShareItemExtractor.make(urls: [URL(string: "file:///tmp/a")!], texts: ["메모", " 메모 "])
        #expect(capture.url == nil)
        #expect(capture.text == "메모")
    }
}

@Suite struct ConfigTests {
    @Test func normalizesServerAddress() {
        #expect(ReceiverConfig(serverURL: "100.1.2.3:8765/", token: "t").baseURL?.absoluteString == "http://100.1.2.3:8765")
        #expect(ReceiverConfig(serverURL: "https://mac.ts.net", token: "t").baseURL?.absoluteString == "https://mac.ts.net")
        #expect(ReceiverConfig(serverURL: "", token: "t").isComplete == false)
        #expect(ReceiverConfig(serverURL: "mac.local:8765", token: "").isComplete == false)
    }

    @Test func readsKeysTheAppWrites() {
        let defaults = UserDefaults(suiteName: "stash-test-\(UUID())")!
        defaults.set("mac.local:8765", forKey: "serverURL")
        defaults.set("abc", forKey: "token")
        #expect(ReceiverConfig.load(defaults) == ReceiverConfig(serverURL: "mac.local:8765", token: "abc"))
    }

    @Test func encodesSnakeCaseKeys() throws {
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(Capture(url: reel, sourceApp: "x"))) as! [String: Any]
        #expect(json["source_app"] as? String == "x")
        #expect(json["captured_at"] is String)
    }
}

/// End-to-end: share-sheet item -> extractor -> ReceiverClient -> real Python receiver -> vault file.
@Suite(.serialized) struct EndToEndTests {
    @Test func reelLandsInVault() async throws {
        let server = try ReceiverProcess()
        defer { server.stop() }
        let client = ReceiverClient(config: ReceiverConfig(serverURL: "127.0.0.1:\(server.port)", token: server.token))

        try await client.health()

        let provider = NSItemProvider(item: URL(string: reel)! as NSURL, typeIdentifier: UTType.url.identifier)
        let capture = await ShareItemExtractor.capture(from: [provider], attachedText: "LLM 위키 관련 릴스",
                                                       sourceApp: "com.burbn.instagram")
        let path = try await client.send(capture)
        #expect(path.hasPrefix("raw/"))

        let note = try String(contentsOf: server.vault.appendingPathComponent(path), encoding: .utf8)
        #expect(note.contains("source: instagram-reel"))
        #expect(note.contains(reel))
        #expect(note.contains("LLM 위키 관련 릴스"))
        #expect(FileManager.default.fileExists(atPath: server.vault.appendingPathComponent("CLAUDE.md").path))
    }

    @Test func wrongTokenAndDeadServerSurfaceClearErrors() async throws {
        let server = try ReceiverProcess()
        let bad = ReceiverClient(config: ReceiverConfig(serverURL: "127.0.0.1:\(server.port)", token: "wrong"))
        await #expect(throws: ReceiverError.unauthorized) { try await bad.send(Capture(url: reel)) }
        server.stop()

        let dead = ReceiverClient(config: ReceiverConfig(serverURL: "127.0.0.1:\(server.port)", token: server.token), timeout: 2)
        do {
            try await dead.send(Capture(url: reel))
            Issue.record("expected unreachable")
        } catch let ReceiverError.unreachable(msg) {
            #expect(!msg.isEmpty)
        }
    }
}

/// Runs server/stash_server.py on a free port with a throwaway vault.
final class ReceiverProcess {
    let process = Process()
    let vault: URL
    let token = UUID().uuidString
    private(set) var port = 0

    init() throws {
        let script = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("server/stash_server.py")
        vault = FileManager.default.temporaryDirectory.appendingPathComponent("stash-e2e-\(UUID())")
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", script.path, "--vault", vault.path, "--host", "127.0.0.1",
                             "--port", "0", "--token", token, "--no-enrich"]
        let stderr = Pipe()
        process.standardError = stderr
        try process.run()

        // Server prints "listening on 127.0.0.1:<port> -> <vault>" once bound.
        var buffer = ""
        let deadline = Date().addingTimeInterval(10)
        while port == 0, Date() < deadline {
            let chunk = stderr.fileHandleForReading.availableData
            if chunk.isEmpty { break }
            buffer += String(decoding: chunk, as: UTF8.self)
            if let range = buffer.range(of: #"(?<=listening on 127\.0\.0\.1:)\d+"#, options: .regularExpression) {
                port = Int(buffer[range]) ?? 0
            }
        }
        guard port != 0 else { process.terminate(); throw CocoaError(.featureUnsupported) }
    }

    func stop() {
        guard process.isRunning else { return }
        process.terminate()
        process.waitUntilExit()
    }

    deinit {
        stop()
        try? FileManager.default.removeItem(at: vault)
    }
}
