// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "CaptureKit",
    platforms: [.iOS(.v16), .macOS(.v14)],
    products: [.library(name: "CaptureKit", targets: ["CaptureKit"])],
    targets: [
        .target(name: "CaptureKit"),
        .testTarget(name: "CaptureKitTests", dependencies: ["CaptureKit"]),
    ]
)
