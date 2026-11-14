#!/bin/zsh
# Put Threshold on Ben's iPhone, on macserver. Both routes need Apple's current Program License Agreement accepted
# at developer.apple.com (Account Holder); until then every call fails with a "required agreement" error.
#
#   ios/scripts/install.sh check        does signing work yet? (one App Store Connect API call, no build)
#   ios/scripts/install.sh usb          build for a device and install on the iPhone plugged into macserver
#   ios/scripts/install.sh testflight   archive, upload to App Store Connect, and it reaches TestFlight
#
# From linuxbox:  on macserver ios/scripts/install.sh <route>
set -euo pipefail
cd "${0:A:h}/../Threshold"
KEY_ID=${ASC_KEY_ID:-PLMMVZAW9U}   # Admin key: needed for cloud-managed distribution signing
ISSUER=${ASC_ISSUER_ID:-f9583201-6a86-49b0-a866-c418cab9223b}
KEY=${ASC_KEY:-$HOME/.appstoreconnect/private_keys/AuthKey_$KEY_ID.p8}
AUTH=(-allowProvisioningUpdates -authenticationKeyPath "$KEY" -authenticationKeyID "$KEY_ID" -authenticationKeyIssuerID "$ISSUER")
HEAVY=$([[ -x ~/bin/heavy ]] && echo ~/bin/heavy || echo)

token() {  # a 20-minute App Store Connect API token, signed with the key
  python3 - "$KEY_ID" "$ISSUER" "$KEY" <<'PY'
import base64, json, subprocess, sys, time
kid, iss, key = sys.argv[1:4]
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
now = int(time.time())
signing = b64(json.dumps({"alg": "ES256", "kid": kid, "typ": "JWT"}).encode()) + "." + b64(json.dumps(
    {"iss": iss, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"}).encode())
der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key], input=signing.encode(), capture_output=True, check=True).stdout
i = 2 if der[1] < 0x80 else 3
l = der[i + 1]; r = der[i + 2:i + 2 + l]; i += 2 + l
l = der[i + 1]; s = der[i + 2:i + 2 + l]
print(signing + "." + b64(r.lstrip(b"\0").rjust(32, b"\0") + s.lstrip(b"\0").rjust(32, b"\0")))
PY
}

case ${1:-check} in
  check)
    out=$(curl -s -H "Authorization: Bearer $(token)" "https://api.appstoreconnect.apple.com/v1/apps?filter%5BbundleId%5D=com.benzhou.threshold")
    if print -r -- "$out" | grep -q REQUIRED_AGREEMENTS; then
      echo "BLOCKED: Apple wants the Account Holder to accept the latest Program License Agreement at developer.apple.com."; exit 2
    fi
    if print -r -- "$out" | grep -q '"bundleId" : "com.benzhou.threshold"'; then
      echo "OK: signing works and the App Store Connect record exists."
    else
      echo "Signing works, but there is no App Store Connect app with bundle com.benzhou.threshold yet."
      echo "Create it at appstoreconnect.apple.com (name Threshold, bundle com.benzhou.threshold) before testflight."
    fi ;;
  usb)
    xcodegen generate -q
    dev=$(xcrun devicectl list devices 2>/dev/null | awk '/iPhone/ && $0 !~ /simulated/ && /connected|available/ {for (i=1;i<=NF;i++) if ($i ~ /^[0-9A-F]{8}-/) {print $i; exit}}')
    [[ -n $dev ]] || { echo "No iPhone connected to macserver: plug it in, unlock it and tap Trust."; exit 3; }
    $HEAVY xcodebuild -scheme Threshold -configuration Release -destination "generic/platform=iOS" -derivedDataPath /tmp/threshold-device "${AUTH[@]}" build
    xcrun devicectl device install app --device "$dev" /tmp/threshold-device/Build/Products/Release-iphoneos/Threshold.app
    xcrun devicectl device process launch --device "$dev" com.benzhou.threshold
    echo "Installed. If iOS says the developer is not trusted: Settings > General > VPN & Device Management > trust it." ;;
  testflight)
    xcodegen generate -q
    rm -rf /tmp/threshold.xcarchive /tmp/threshold-export
    $HEAVY xcodebuild -scheme Threshold -configuration Release -destination "generic/platform=iOS" -archivePath /tmp/threshold.xcarchive "${AUTH[@]}" archive
    xcodebuild -exportArchive -archivePath /tmp/threshold.xcarchive -exportOptionsPlist ../scripts/ExportOptions.plist -exportPath /tmp/threshold-export "${AUTH[@]}"
    echo "Uploaded. App Store Connect processes the build for about 10 minutes, then it shows in TestFlight on the phone." ;;
  *) echo "usage: $0 check|usb|testflight"; exit 1 ;;
esac
