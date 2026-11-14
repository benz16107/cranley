import Foundation
import Observation

/// Where the server is, the pairing token of the desktop workspace the phone is linked to, and the scans sent from
/// this phone.
@Observable
final class AppModel {
  var server: URL { didSet { UserDefaults.standard.set(server.absoluteString, forKey: "server") } }
  /// The pairing token from the desktop's Phone link, or nil when the phone is not linked. It is not the workspace id.
  var workspace: String? { didSet { UserDefaults.standard.set(workspace, forKey: "workspace") } }
  var scans: [UserScan] = []
  var lastError: String?

  init() {
    let saved = UserDefaults.standard.string(forKey: "server").flatMap(URL.init(string:))
    server = saved ?? URL(string: "http://linuxbox:8787")!
    workspace = UserDefaults.standard.string(forKey: "workspace")
  }

  var api: ThresholdAPI { ThresholdAPI(base: server) }
  var capture: CaptureClient { CaptureClient(base: server, token: workspace) }

  /// Link to a workspace from the desktop's Phone link. Returns false when the link carries no token.
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

/// The server and pairing token in the desktop's Phone link, `<server>/m?t=<token>` (POST /api/workspace/{id}/pair).
struct WorkspaceLink: Equatable {
  var server: URL
  var workspace: String  // the pairing token

  init?(_ text: String) {
    guard let parts = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
          let scheme = parts.scheme, scheme.hasPrefix("http"), let host = parts.host,
          let token = parts.queryItems?.first(where: { $0.name == "t" })?.value, !token.isEmpty,
          token.allSatisfy({ $0.isLetter || $0.isNumber || "_-.".contains($0) }) else { return nil }
    var base = URLComponents()
    base.scheme = scheme
    base.host = host
    base.port = parts.port
    guard let url = base.url else { return nil }
    server = url
    workspace = token
  }
}
