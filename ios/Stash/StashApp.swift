import CaptureKit
import SwiftUI

@main
struct StashApp: App {
    var body: some Scene {
        WindowGroup { SettingsView() }
    }
}

/// The app itself only holds the Mac address + token; saving happens in the share extension.
/// @AppStorage writes every keystroke straight to the App Group, where the extension reads it.
struct SettingsView: View {
    @AppStorage("serverURL", store: UserDefaults(suiteName: ReceiverConfig.appGroup)) private var serverURL = ""
    @AppStorage("token", store: UserDefaults(suiteName: ReceiverConfig.appGroup)) private var token = ""
    @State private var status: String?
    @State private var testing = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("100.101.132.63:8765", text: $serverURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .accessibilityIdentifier("serverURL")
                    SecureField("토큰", text: $token)
                        .accessibilityIdentifier("token")
                } header: {
                    Text("Mac 수신 서버")
                } footer: {
                    Text("Mac에서 server/run.sh 를 켜면 주소와 토큰이 출력됩니다. Tailscale 주소를 쓰면 밖에서도 저장됩니다.")
                }

                Section {
                    Button(testing ? "확인 중…" : "연결 테스트") { Task { await test() } }
                        .disabled(testing || !config.isComplete)
                        .accessibilityIdentifier("testConnection")
                    if let status {
                        Text(status).accessibilityIdentifier("status")
                    }
                }

                Section("사용법") {
                    Label("인스타그램 릴스 → 공유 → 공유하기(⋯)", systemImage: "1.circle")
                    Label("공유 시트에서 Stash 탭", systemImage: "2.circle")
                    Label("Mac 볼트 raw/ 에 저장 → LLM 위키로 정리", systemImage: "3.circle")
                }
            }
            .navigationTitle("Stash")
        }
    }

    private var config: ReceiverConfig { ReceiverConfig(serverURL: serverURL, token: token) }

    private func test() async {
        testing = true
        defer { testing = false }
        do {
            try await ReceiverClient(config: config).health()
            status = "✅ 연결됨"
        } catch {
            status = "⚠️ \(error.localizedDescription)"
        }
    }
}
