import XCTest

/// Walks a field visit in the simulator and saves screenshots: the test cafe as the scan, the report form, the checks
/// running, the finished visit and the report PDF. Needs a Threshold server; pass it as THRESHOLD_SERVER
/// (default http://linuxbox:8843). Screenshots go to THRESHOLD_SHOTS (default /tmp/threshold-shots) on the Mac.
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
  func testFieldVisit() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-server", env["THRESHOLD_SERVER"] ?? "http://linuxbox:8843"]
    app.launch()

    XCTAssertTrue(app.navigationBars["Site visits"].waitForExistence(timeout: 10))
    shot("01-home")

    app.buttons["Use the test cafe"].tap()
    XCTAssertTrue(app.navigationBars["New report"].waitForExistence(timeout: 5))
    let business = app.textFields["business"]
    XCTAssertTrue(business.waitForExistence(timeout: 5))
    business.tap()
    business.typeText("Test Cafe (made up)")
    let space = app.textFields["place"]
    space.tap()
    space.typeText("Ground floor shop")
    app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Fire safety pre-plan'")).firstMatch.tap()
    shot("02-report-form")

    app.navigationBars["New report"].buttons["Send"].tap()
    let finished = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'checks finished'")).firstMatch
    XCTAssertTrue(finished.waitForExistence(timeout: 120), "the visit's checks did not finish")
    sleep(1)
    shot("03-visit-finished")
    app.swipeUp()
    sleep(1)
    shot("04-visit-on-site")
    app.swipeDown()

    app.buttons["Open report"].tap()
    sleep(12)  // the server prints the PDF, then Quick Look opens it
    shot("05-report")
    app.swipeUp()
    sleep(1)
    shot("06-report-more")
  }
}
