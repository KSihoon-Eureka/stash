import Foundation

public enum ReceiverError: LocalizedError, Equatable {
    case notConfigured
    case unauthorized
    case server(Int, String)
    case unreachable(String)

    public var errorDescription: String? {
        switch self {
        case .notConfigured: return "Stash 앱에서 Mac 주소와 토큰을 먼저 설정하세요."
        case .unauthorized: return "토큰이 맞지 않습니다."
        case let .server(code, msg): return "Mac 서버 오류 (\(code)): \(msg)"
        case let .unreachable(msg): return "Mac에 연결할 수 없습니다: \(msg)"
        }
    }
}

public struct ReceiverClient: Sendable {
    public let config: ReceiverConfig
    let session: URLSession

    public init(config: ReceiverConfig, timeout: TimeInterval = 8) {
        self.config = config
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = timeout
        cfg.waitsForConnectivity = false
        self.session = URLSession(configuration: cfg)
    }

    /// Sends a capture; returns the vault-relative path the Mac wrote.
    @discardableResult
    public func send(_ capture: Capture) async throws -> String {
        var req = try request("capture")
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(capture)
        let body = try await perform(req)
        return body["path"] as? String ?? ""
    }

    public func health() async throws {
        _ = try await perform(try request("health"))
    }

    private func request(_ path: String) throws -> URLRequest {
        guard config.isComplete, let base = config.baseURL else { throw ReceiverError.notConfigured }
        var req = URLRequest(url: base.appendingPathComponent(path))
        req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
        return req
    }

    private func perform(_ req: URLRequest) async throws -> [String: Any] {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw ReceiverError.unreachable(error.localizedDescription)
        }
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        if code == 401 { throw ReceiverError.unauthorized }
        guard (200..<300).contains(code) else {
            throw ReceiverError.server(code, json["error"] as? String ?? "")
        }
        return json
    }
}
