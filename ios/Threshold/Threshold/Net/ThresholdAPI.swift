import Foundation

/// The Threshold server's routes the phone uses (Contract 2 plus POST /api/scans/user).
nonisolated struct ThresholdAPI: Sendable {
  var base: URL

  struct Failure: LocalizedError {
    var status: Int
    var message: String
    var errorDescription: String? { "The server answered \(status): \(message)" }
  }

  func send(_ method: String, _ path: String, query: [URLQueryItem] = [], body: Data? = nil) async throws -> Data {
    var parts = URLComponents(url: base.appending(path: path), resolvingAgainstBaseURL: false)!
    if !query.isEmpty {
      parts.queryItems = query
      parts.percentEncodedQuery = parts.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")  // servers read + as a space
    }
    var request = URLRequest(url: parts.url!, timeoutInterval: 120)
    request.httpMethod = method
    if let body {
      request.httpBody = body
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    let (data, response) = try await URLSession.shared.data(for: request)
    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
    guard (200..<300).contains(status) else {
      let detail = (try? JSONDecoder().decode([String: String].self, from: data))?["detail"]
      throw Failure(status: status, message: detail ?? String(decoding: data.prefix(300), as: UTF8.self))
    }
    return data
  }

  func get<T: Decodable>(_ path: String, query: [URLQueryItem] = [], as: T.Type = T.self) async throws -> T {
    try JSONDecoder().decode(T.self, from: try await send("GET", path, query: query))
  }

  // MARK: phone scans

  /// Upload a RoomPlan export (the JSON of a CapturedRoom or CapturedStructure). The server converts it to a ScanPlan.
  func uploadScan(export: Data, name: String, kind: String?, address: String?, geo: ScanGeo?, workspace: String?) async throws -> UploadResult {
    var body: [String: Any] = ["export": try JSONSerialization.jsonObject(with: export), "name": name]
    if let kind { body["kind"] = kind }
    if let address { body["address"] = address }
    if let workspace { body["workspace"] = workspace }
    if let geo { body["geo"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(geo)) }
    let data = try await send("POST", "api/scans/user", body: try JSONSerialization.data(withJSONObject: body))
    return try JSONDecoder().decode(UploadResult.self, from: data)
  }

  func userScans(workspace: String?) async throws -> [UserScan] {
    try await get("api/scans/user", query: workspace.map { [URLQueryItem(name: "workspace", value: $0)] } ?? [])
  }

  func plan(_ sid: String) async throws -> ScanPlan { try await get("api/scan/\(sid)/plan") }

  // MARK: tools

  /// Run a tool on its own (not inside a workspace) and return its verdict.
  func runTool(_ id: String, inputs: [String: any Sendable]) async throws -> ToolOutcome {
    let data = try await send("POST", "api/tools/\(id)/run", body: try JSONSerialization.data(withJSONObject: inputs))
    return try JSONDecoder().decode(ToolOutcome.self, from: data)
  }
}

nonisolated struct ScanGeo: Codable, Sendable {
  var lat: Double
  var lon: Double
  var altitude: Double?
  var accuracy_m: Double?
  var heading_deg: Double?
  var heading_accuracy_deg: Double?
  var camera_forward: [Double]?   // RoomPlan world X, Z
  var camera_position: [Double]?  // RoomPlan world X, Z
}

nonisolated struct UploadResult: Decodable, Sendable {
  struct Room: Decodable, Sendable, Identifiable { var id: String; var label: String?; var area: Double? }
  var sid: String
  var name: String
  var rooms: [Room]
  var notes: [String]
}

nonisolated struct UserScan: Decodable, Sendable, Identifiable, Hashable {
  var sid: String
  var name: String?
  var kind: String?
  var address: String?
  var created: String?
  var workspace: String?
  var id: String { sid }
}

nonisolated struct ToolOutcome: Decodable, Sendable {
  struct Verdict: Decodable, Sendable { var status: String; var text: String }
  struct Metric: Decodable, Sendable, Identifiable {
    var id: String
    var label: String
    var value: Double?
    var unit: String?
    enum CodingKeys: String, CodingKey { case id, label, value, unit }
    init(from d: any Decoder) throws {
      let c = try d.container(keyedBy: CodingKeys.self)
      id = try c.decode(String.self, forKey: .id)
      label = try c.decode(String.self, forKey: .label)
      value = try? c.decodeIfPresent(Double.self, forKey: .value)  // some metrics carry text
      unit = try c.decodeIfPresent(String.self, forKey: .unit)
    }
  }
  var verdict: Verdict
  var metrics: [Metric]?
}
