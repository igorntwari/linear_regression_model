import Flutter
import UIKit
import XCTest

class RunnerTests: XCTestCase {

  func testAppIdentity() {
    XCTAssertEqual(Bundle.main.bundleIdentifier, "rw.nyaruka.solarpredictor")
    XCTAssertEqual(Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String, "Solar Predictor")
  }

}
