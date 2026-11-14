import Foundation

/// Field visits and their reports (server/threshold/api/report.py): a scan becomes a visit whose tools run on the
/// server, and the visit prints as a PDF.
extension ThresholdAPI {
  enum ReportKind: String, Codable, Sendable, CaseIterable, Identifiable {
    case accessibility, fire, fitout
    var id: String { rawValue }
    var title: String {
      switch self {
      case .accessibility: "Accessibility audit"
      case .fire: "Fire safety pre-plan"
      case .fitout: "Fit-out and occupancy"
      }
    }
    var detail: String {
      switch self {
      case .accessibility: "Door widths, a step-free route, turning space and the restroom, against the ADA."
      case .fire: "Occupant load, ways out, walking distances and the NFPA 1620 pre-plan, plus ceiling photos for smoke alarms."
      case .fitout: "Room areas, how many people it seats, door widths for deliveries, windows and a cleaning estimate."
      }
    }
    var symbol: String {
      switch self {
      case .accessibility: "figure.roll"
      case .fire: "flame"
      case .fitout: "square.split.bottomrightquarter"
      }
    }
  }

  struct VisitStart: Decodable, Sendable {
    var workspace: String
    var token: String
    var status: VisitStatus
  }

  struct VisitStatus: Decodable, Sendable {
    struct Tool: Decodable, Sendable, Identifiable {
      var tool: String
      var title: String
      var status: String  // waiting, running, done, error, skipped
      var verdict: ToolOutcome.Verdict?
      var error: String?
      var id: String { tool }
    }
    var workspace: String
    var tools: [Tool]
    var done: Bool
  }

  func startVisit(sid: String, kind: ReportKind, business: String, place: String, address: String) async throws -> VisitStart {
    let body = ["sid": sid, "kind": kind.rawValue, "business": business, "place": place, "address": address]
    let data = try await send("POST", "api/report/visit", body: try JSONSerialization.data(withJSONObject: body))
    return try JSONDecoder().decode(VisitStart.self, from: data)
  }

  func visitStatus(_ workspace: String) async throws -> VisitStatus { try await get("api/report/\(workspace)/status") }

  /// The report PDF, saved to a temporary file named for the business so a share sheet shows a sensible name.
  func reportPDF(_ workspace: String, name: String) async throws -> URL {
    let data = try await send("GET", "api/report/\(workspace).pdf")
    let safe = name.components(separatedBy: CharacterSet.alphanumerics.union(.whitespaces).inverted).joined()
      .trimmingCharacters(in: .whitespaces)
    let url = FileManager.default.temporaryDirectory.appending(path: "\(safe.isEmpty ? "Threshold report" : safe).pdf")
    try data.write(to: url, options: .atomic)
    return url
  }
}

/// A visit this phone started, kept on the phone so its report can be opened again.
nonisolated struct VisitRecord: Codable, Sendable, Identifiable, Hashable {
  var workspace: String
  var token: String
  var sid: String
  var kind: ThresholdAPI.ReportKind
  var business: String
  var place: String
  var started: Date
  var id: String { workspace }
  var name: String { business.isEmpty ? (place.isEmpty ? "Site visit" : place) : business }
}
