import Foundation

/// The capture API that `ws/mobile` owns (server/threshold/api/capture.py). It did not exist when this was written,
/// so this is the shape written down in reports/core-requests.md under "iOS". Everything that depends on that
/// contract is in this one file.
nonisolated struct CaptureClient: Sendable {
  var base: URL

  enum Kind: String, Codable, Sendable, CaseIterable {
    case doorWidth = "door_width", thresholdHeight = "threshold_height", stepHeight = "step_height"
    case ceilingHeight = "ceiling_height", floorHeight = "floor_height", windowFacing = "window_facing", photo
  }

  struct Task: Decodable, Sendable, Identifiable, Hashable {
    var id: String
    var kind: Kind?
    var title: String
    var detail: String?
    var sid: String?
    var finding: String?
    var status: String?
  }

  struct Measurement: Encodable, Sendable {
    var workspace: String?
    var task: String?
    var finding: String?
    var sid: String?
    var kind: Kind
    var value: Double
    var unit: String
    var method: String              // "arkit_lidar" | "barometer" | "compass"
    var accuracy: Double?
    var points: [[Double]]?         // ARKit world metres, y up
    var device: String = Device.model
    var app: String = "threshold-ios/1"
    var taken_at: String = ISO8601DateFormatter().string(from: .now)
    var location: Location?
    var photo_jpeg_base64: String?

    struct Location: Encodable, Sendable { var lat: Double; var lon: Double; var accuracy_m: Double }
  }

  /// Open field tasks for a workspace. Falls back to the workspace's findings that need a look on site while the
  /// capture API is not there (404).
  func tasks(workspace: String) async throws -> [Task] {
    let api = ThresholdAPI(base: base)
    do {
      let all: [Task] = try await api.get("api/capture/tasks", query: [URLQueryItem(name: "workspace", value: workspace)])
      return all.filter { $0.status != "done" }
    } catch let failure as ThresholdAPI.Failure where failure.status == 404 || failure.status == 405 {
      let findings = try await api.workspace(workspace).doc.findings ?? []
      return findings
        .filter { $0.result == "measure on site" || $0.status == "warn" || $0.status == "unknown" }
        .map { Task(id: $0.id, kind: Self.kind(for: $0), title: $0.title, detail: $0.detail, sid: nil, finding: $0.id) }
    }
  }

  @discardableResult
  func send(_ m: Measurement) async throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = .withoutEscapingSlashes
    return try await ThresholdAPI(base: base).send("POST", "api/capture", body: try encoder.encode(m))
  }

  /// Guess which measurement answers a finding, from its title. Only a default: the person picks the tool.
  static func kind(for f: WorkspaceDoc.Finding) -> Kind? {
    let t = f.title.lowercased()
    if t.contains("ceiling") { return .ceilingHeight }
    if t.contains("threshold") { return .thresholdHeight }
    if t.contains("step") || t.contains("stair") { return .stepHeight }
    if t.contains("door") || t.contains("width") || t.contains("narrow") { return .doorWidth }
    if t.contains("floor height") || t.contains("flood") || t.contains("water") { return .floorHeight }
    if t.contains("window") || t.contains("sun") || t.contains("facing") { return .windowFacing }
    return nil
  }
}

nonisolated enum Device {
  static let model: String = {
    var info = utsname()
    uname(&info)
    return withUnsafeBytes(of: &info.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
  }()
}
