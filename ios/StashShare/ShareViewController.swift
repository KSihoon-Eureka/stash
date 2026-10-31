import CaptureKit
import UIKit

/// Tapping "Stash" in the share sheet saves immediately — no compose step.
/// Shows a small status card, then dismisses itself on success.
final class ShareViewController: UIViewController {
    private let card = UIView()
    private let icon = UIImageView()
    private let label = UILabel()
    private let spinner = UIActivityIndicatorView(style: .medium)
    private let retryButton = UIButton(type: .system)
    private let closeButton = UIButton(type: .system)
    private var started = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor.black.withAlphaComponent(0.25)

        card.backgroundColor = .secondarySystemBackground
        card.layer.cornerRadius = 18
        label.font = .preferredFont(forTextStyle: .headline)
        label.numberOfLines = 0
        label.textAlignment = .center
        icon.contentMode = .scaleAspectFit
        icon.tintColor = .systemGreen
        retryButton.setTitle("다시 시도", for: .normal)
        retryButton.addAction(UIAction { [weak self] _ in self?.save() }, for: .touchUpInside)
        closeButton.setTitle("닫기", for: .normal)
        closeButton.addAction(UIAction { [weak self] _ in self?.finish() }, for: .touchUpInside)

        let buttons = UIStackView(arrangedSubviews: [closeButton, retryButton])
        buttons.spacing = 24
        let stack = UIStackView(arrangedSubviews: [spinner, icon, label, buttons])
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        card.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(stack)
        view.addSubview(card)
        NSLayoutConstraint.activate([
            card.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            card.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            card.widthAnchor.constraint(equalToConstant: 260),
            icon.heightAnchor.constraint(equalToConstant: 44),
            stack.topAnchor.constraint(equalTo: card.topAnchor, constant: 24),
            stack.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -20),
            stack.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -20),
        ])
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !started else { return }
        started = true
        save()
    }

    private func save() {
        show(.saving)
        let items = extensionContext?.inputItems as? [NSExtensionItem] ?? []
        let providers = items.flatMap { $0.attachments ?? [] }
        let attachedText = items.compactMap { $0.attributedContentText?.string }.joined(separator: "\n")

        Task { @MainActor in
            let capture = await ShareItemExtractor.capture(from: providers, attachedText: attachedText)
            guard !capture.isEmpty else { return show(.failed("저장할 링크나 텍스트가 없습니다.")) }
            do {
                try await ReceiverClient(config: .load()).send(capture)
                show(.saved)
                try? await Task.sleep(nanoseconds: 700_000_000)
                finish()
            } catch {
                show(.failed(error.localizedDescription))
            }
        }
    }

    private enum State { case saving, saved, failed(String) }

    private func show(_ state: State) {
        var failed = false
        switch state {
        case .saving:
            spinner.startAnimating()
            icon.isHidden = true
            label.text = "Mac에 저장 중…"
        case .saved:
            spinner.stopAnimating()
            icon.isHidden = false
            icon.image = UIImage(systemName: "checkmark.circle.fill")
            icon.tintColor = .systemGreen
            label.text = "저장됨"
        case let .failed(message):
            failed = true
            spinner.stopAnimating()
            icon.isHidden = false
            icon.image = UIImage(systemName: "exclamationmark.triangle.fill")
            icon.tintColor = .systemOrange
            label.text = message
        }
        retryButton.isHidden = !failed
        closeButton.isHidden = !failed
    }

    private func finish() {
        extensionContext?.completeRequest(returningItems: nil)
    }
}
