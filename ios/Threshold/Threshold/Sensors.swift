import CoreLocation
import CoreMotion
import Observation

/// GPS position and compass heading. Heading is true north when location is allowed, else magnetic.
@Observable
final class LocationSensor: NSObject, CLLocationManagerDelegate {
  var location: CLLocation?
  var headingDegrees: Double?     // clockwise from north; true north when location is allowed, else magnetic
  var headingAccuracy: Double?    // degrees
  var authorized = false
  private let manager = CLLocationManager()

  override init() {
    super.init()
    manager.delegate = self
    manager.desiredAccuracy = kCLLocationAccuracyBest
    manager.headingOrientation = .portrait
  }

  func start() {
    manager.requestWhenInUseAuthorization()
    manager.startUpdatingLocation()
    if CLLocationManager.headingAvailable() { manager.startUpdatingHeading() }
  }

  func stop() {
    manager.stopUpdatingLocation()
    manager.stopUpdatingHeading()
  }

  nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
    let last = locations.last
    MainActor.assumeIsolated { location = last }
  }

  nonisolated func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
    guard newHeading.headingAccuracy >= 0 else { return }  // negative: no valid reading
    let deg = newHeading.trueHeading >= 0 ? newHeading.trueHeading : newHeading.magneticHeading
    let accuracy = newHeading.headingAccuracy
    MainActor.assumeIsolated { headingDegrees = deg; headingAccuracy = accuracy }
  }

  nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
    let status = manager.authorizationStatus
    MainActor.assumeIsolated { authorized = status == .authorizedWhenInUse || status == .authorizedAlways }
  }
}

/// The barometer's change in height since `start()`, in metres.
@Observable
final class Barometer {
  var available: Bool { CMAltimeter.isRelativeAltitudeAvailable() }
  var samples: [(time: Date, metres: Double)] = []
  var latest: Double? { samples.last?.metres }
  private let altimeter = CMAltimeter()

  func start() {
    samples = []
    altimeter.startRelativeAltitudeUpdates(to: .main) { [weak self] data, _ in
      guard let data else { return }
      let metres = data.relativeAltitude.doubleValue
      MainActor.assumeIsolated { self?.samples.append((Date(), metres)) }
    }
  }

  func stop() { altimeter.stopRelativeAltitudeUpdates() }

  /// Mean height over the last few seconds, so a held-still phone reads steady. The spread is the standard deviation.
  func settled(seconds: Double = 4) -> (metres: Double, spread: Double)? {
    let cutoff = Date().addingTimeInterval(-seconds)
    let recent = samples.filter { $0.time >= cutoff }.map(\.metres)
    guard !recent.isEmpty else { return nil }
    let mean = recent.reduce(0, +) / Double(recent.count)
    let sd = (recent.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Double(recent.count)).squareRoot()
    return (mean, sd)
  }
}

enum Compass {
  static let points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
  static func word(_ degrees: Double) -> String { points[Int((degrees.truncatingRemainder(dividingBy: 360) + 371.25) / 22.5) % 16] }
}
