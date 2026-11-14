import Foundation
import Observation

/// Where the server is, which desktop workspace the phone is attached to, and the scans sent from this phone.
@Observable
final class AppModel {
  var server: URL { didSet { UserDefaults.standard.set(server.absoluteString, forKey: "server") } }
  var workspace: String? { didSet { UserDefaults.standard.set(workspace, forKey: "workspace") } }
  var scans: [UserScan] = []
  var lastError: String?

  init() {
    let saved = UserDefaults.standard.string(forKey: "server").flatMap(URL.init(string:))
    server = saved ?? URL(string: "http://linuxbox:8787")!
    workspace = UserDefaults.standard.string(forKey: "workspace")
  }

  var api: ThresholdAPI { ThresholdAPI(base: server) }
  var capture: CaptureClient { CaptureClient(base: server) }

  /// Attach to a workspace from the desktop's "Continue on phone" link. Returns false when the link names none.
  @discardableResult
  func link(_ text: String) -> Bool {
    guard let link = WorkspaceLink(text) else { return false }
    server = link.server
    workspace = link.workspace
    return true
  }

  func refreshScans() async {
    do {
      scans = try await api.userScans(workspace: nil)
      lastError = nil
    } catch {
      lastError = error.localizedDescription
    }
  }
}

/// The server and workspace a "Continue on phone" link points at. The workspace id is query `workspace` or `w`, or
/// the path segment after `/w/` or `/workspace/`.
struct WorkspaceLink: Equatable {
  var server: URL
  var workspace: String

  init?(_ text: String) {
    guard let parts = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
          let scheme = parts.scheme, scheme.hasPrefix("http"), let host = parts.host else { return nil }
    let query = parts.queryItems ?? []
    let fromQuery = query.first { $0.name == "workspace" }?.value ?? query.first { $0.name == "w" }?.value
    let path = parts.path.split(separator: "/").map(String.init)
    let fromPath = path.firstIndex { $0 == "w" || $0 == "workspace" }.flatMap { $0 + 1 < path.count ? path[$0 + 1] : nil }
    guard let id = fromQuery ?? fromPath, !id.isEmpty,
          id.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" }) else { return nil }
    var base = URLComponents()
    base.scheme = scheme
    base.host = host
    base.port = parts.port
    guard let url = base.url else { return nil }
    server = url
    workspace = id
  }
}
