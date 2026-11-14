import Foundation

/// The capture API (server/threshold/api/capture.py), the same one the web companion at /m uses. The phone holds a
/// pairing token from the desktop's Phone link (`/m?t=<token>`) and every call is made with it. Everything that
/// depends on that contract is in this one file.
nonisolated struct CaptureClient: Sendable {
  var base: URL
  var token: String?

  struct NotLinked: LocalizedError {
    var errorDescription: String? { "Link a workspace first: Workspace tab, then scan the code on your computer." }
  }

  enum Kind: String, Codable, Sendable, CaseIterable {
    case doorWidth = "door_width", thresholdHeight = "threshold_height", stepHeight = "step_height"
    case ceilingHeight = "ceiling_height", floorHeight = "floor_height", windowFacing = "window_facing", photo
  }

  /// A phone task from the server (capture/tasks.py). `kind` is the measurement in this app that answers it, or nil
  /// when only the web companion can (a smoke alarm photo, a ramp slope).
  struct Task: Decodable, Sendable, Identifiable, Hashable {
    var id: String
    var kind: Kind?
    var title: String
    var detail: String?
    var sid: String?
    var finding: String?
    var status: String?

    static let kinds: [String: Kind] = ["width": .doorWidth, "step": .stepHeight, "floor_height": .floorHeight, "heading": .windowFacing]
    enum CodingKeys: String, CodingKey { case id, kind, title, detail = "why", sid, findings, status }
    init(from d: any Decoder) throws {
      let c = try d.container(keyedBy: CodingKeys.self)
      id = try c.decode(String.self, forKey: .id)
      kind = Self.kinds[try c.decode(String.self, forKey: .kind)]
      title = try c.decode(String.self, forKey: .title)
      detail = try c.decodeIfPresent(String.self, forKey: .detail)
      sid = try c.decodeIfPresent(String.self, forKey: .sid)
      finding = try c.decodeIfPresent([String].self, forKey: .findings)?.first
      status = try c.decodeIfPresent(String.self, forKey: .status)
    }
  }

  struct Measurement: Sendable {
    var task: String?
    var finding: String?
    var sid: String?
    var kind: Kind
    var value: Double
    var unit: String
    var method: String              // "arkit_lidar" | "barometer" | "compass"
    var accuracy: Double?
    var points: [[Double]]?         // ARKit world metres, y up
    var location: Location?
    var photo: Data?                // JPEG

    struct Location: Sendable { var lat: Double; var lon: Double; var accuracy_m: Double }
  }

  /// What the server made of a capture: why it settled nothing, or what it now says.
  struct Reply: Decodable, Sendable {
    struct Outcome: Decodable, Sendable { var text: String? }
    var problem: String?
    var text: String?
    var outcome: Outcome?
    var says: String? { problem ?? outcome?.text ?? text }
  }

  /// Open field tasks of the linked workspace.
  func tasks() async throws -> [Task] {
    guard let token else { return [] }
    struct PhoneView: Decodable { var tasks: [Task] }
    let view: PhoneView = try await ThresholdAPI(base: base).get("api/phone/\(token)")
    return view.tasks.filter { $0.status != "done" }
  }

  /// Add a scan to the linked workspace's buildings, so the desktop and its tools can use it.
  func place(_ sid: String) async throws {
    guard let token else { throw NotLinked() }
    _ = try await ThresholdAPI(base: base).send("POST", "api/phone/\(token)/place", body: try JSONSerialization.data(withJSONObject: ["sid": sid]))
  }

  /// Send one measurement as a capture record (capture/store.py `Meta`), with its photo as the request body.
  @discardableResult
  func send(_ m: Measurement) async throws -> Reply {
    guard let token else { throw NotLinked() }
    var values: [String: Any] = ["unit": m.unit, "sensor": m.method]
    if let a = m.accuracy { values["err_m"] = a }
    if let p = m.points { values["points"] = p }
    var meta: [String: Any] = ["kind": m.photo == nil ? "reading" : "photo", "device": "\(Device.model) threshold-ios/1",
                               "taken": Date.now.timeIntervalSince1970]
    switch m.kind {
    case .floorHeight: values["baro_rise_m"] = m.value
    case .windowFacing:
      meta["heading_deg"] = m.value.truncatingRemainder(dividingBy: 360)
      if let a = m.accuracy, a >= 0 { meta["heading_accuracy_deg"] = a }
      values["err_m"] = nil
    default: values["value_m"] = m.value
    }
    meta["values"] = values
    if m.task == nil {  // no task to settle: the server keeps it as a note, so the note carries the reading
      meta["note"] = "\(m.kind.rawValue.replacingOccurrences(of: "_", with: " ")): \(String(format: "%.2f", m.value)) \(m.unit), measured with \(m.method)"
    }
    if let t = m.task { meta["task"] = t } else if m.kind == .floorHeight, m.sid != nil { meta["tool"] = "floor_height" }
    if let s = m.sid { meta["scan"] = s }
    if let f = m.finding { meta["finding"] = f }
    if let l = m.location {
      var fix: [String: Any] = ["lat": l.lat, "lon": l.lon]
      if l.accuracy_m >= 0 { fix["accuracy_m"] = l.accuracy_m }
      meta["fix"] = fix
    }
    let json = String(decoding: try JSONSerialization.data(withJSONObject: meta), as: UTF8.self)
    let data = try await ThresholdAPI(base: base).send("POST", "api/phone/\(token)/capture",
                                                       query: [URLQueryItem(name: "meta", value: json)], body: m.photo)
    return (try? JSONDecoder().decode(Reply.self, from: data)) ?? Reply()
  }
}

nonisolated enum Device {
  static let model: String = {
    var info = utsname()
    uname(&info)
    return withUnsafeBytes(of: &info.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
  }()
}
