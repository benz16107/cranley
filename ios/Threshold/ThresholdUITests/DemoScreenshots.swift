import XCTest

/// Walks the demo path in the simulator and saves screenshots: send the sample home, see its plan and the tools'
/// verdicts, then the Measure and Workspace tabs. Needs a Threshold server; pass it as THRESHOLD_SERVER
/// (default http://linuxbox:8811). Screenshots go to THRESHOLD_SHOTS (default /tmp/threshold-shots) on the Mac.
final class DemoScreenshots: XCTestCase {
  let env = ProcessInfo.processInfo.environment

  @MainActor
  func shot(_ name: String) {
    let png = XCUIScreen.main.screenshot().pngRepresentation
    let dir = URL(fileURLWithPath: env["THRESHOLD_SHOTS"] ?? "/tmp/threshold-shots")
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    try? png.write(to: dir.appendingPathComponent("\(name).png"))
    let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png")
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }

  @MainActor
  func testDemoPath() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-server", env["THRESHOLD_SERVER"] ?? "http://linuxbox:8787"]
    if let ws = env["THRESHOLD_WORKSPACE"] { app.launchArguments += ["-workspace", ws] }
    app.launch()

    XCTAssertTrue(app.navigationBars["Your home"].waitForExistence(timeout: 10))
    shot("01-home")

    app.buttons["Send the sample home"].tap()
    XCTAssertTrue(app.staticTexts["Rooms"].waitForExistence(timeout: 30), "the sample home did not open")
    let doorVerdict = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'doorways are narrower'")).firstMatch
    XCTAssertTrue(doorVerdict.waitForExistence(timeout: 60), "tool verdicts did not arrive")
    sleep(2)
    shot("02-scan-plan")

    app.swipeUp()
    sleep(1)
    shot("03-scan-tools")
    app.swipeUp()
    sleep(1)
    shot("04-scan-tools-more")

    app.tabBars.buttons["Measure"].tap()
    XCTAssertTrue(app.navigationBars["Measure"].waitForExistence(timeout: 5))
    shot("05-measure")
    app.buttons["Floor above street"].tap()
    sleep(1)
    shot("06-floor-height")

    app.tabBars.buttons["Workspace"].tap()
    XCTAssertTrue(app.navigationBars["Workspace"].waitForExistence(timeout: 5))
    shot("07-workspace")
  }
}
