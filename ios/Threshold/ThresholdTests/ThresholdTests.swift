import Foundation
import RoomPlan
import Testing
@testable import Threshold

struct WorkspaceLinkTests {
  @Test(arguments: [
    ("http://linuxbox:8787/phone?workspace=ws_abc123", "http://linuxbox:8787", "ws_abc123"),
    ("https://linuxbox.<tailnet>/m?w=abc-9", "https://linuxbox.<tailnet>", "abc-9"),
    ("http://192.168.18.70:5173/w/xyz/phone", "http://192.168.18.70:5173", "xyz"),
    ("  http://linuxbox:8787/workspace/k1  ", "http://linuxbox:8787", "k1"),
  ])
  func `reads the server and the workspace`(link: String, server: String, workspace: String) throws {
    let parsed = try #require(WorkspaceLink(link))
    #expect(parsed.server.absoluteString == server)
    #expect(parsed.workspace == workspace)
  }

  @Test(arguments: ["http://linuxbox:8787/", "linuxbox:8787?w=a", "http://x/?w=a%20b", "not a link"])
  func `refuses links without a usable workspace`(link: String) {
    #expect(WorkspaceLink(link) == nil)
  }
}

struct DemoExportTests {
  /// The sample home is exactly what a real scan sends: Apple's own CapturedRoom decoder must accept it.
  @Test func `the sample home decodes as a CapturedRoom`() throws {
    let url = try #require(Bundle(for: Probe.self).url(forResource: "DemoHome", withExtension: "json")
      ?? Bundle.main.url(forResource: "DemoHome", withExtension: "json"))
    let room = try JSONDecoder().decode(CapturedRoom.self, from: Data(contentsOf: url))
    #expect(room.walls.count == 9)
    #expect(room.doors.count == 5)
    #expect(room.windows.count == 5)
    #expect(room.objects.contains { $0.category == .bathtub })
    let again = try JSONEncoder().encode(room)  // and encodes back to what the server converts
    let object = try JSONSerialization.jsonObject(with: again) as? [String: Any]
    #expect((object?["walls"] as? [Any])?.count == 9)
  }
}

final class Probe {}

struct CompassTests {
  @Test(arguments: [(0.0, "N"), (11.0, "N"), (12.0, "NNE"), (90.0, "E"), (181.0, "S"), (350.0, "N"), (292.0, "WNW")])
  func `names the compass point`(degrees: Double, word: String) {
    #expect(Compass.word(degrees) == word)
  }
}
