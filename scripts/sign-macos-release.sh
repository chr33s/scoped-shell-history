#!/usr/bin/env bash
set -euo pipefail
for variable in DEVELOPER_ID_CERTIFICATE_BASE64 DEVELOPER_ID_CERTIFICATE_PASSWORD \
  DEVELOPER_ID_APPLICATION KEYCHAIN_PASSWORD APPLE_ID APPLE_TEAM_ID APPLE_APP_SPECIFIC_PASSWORD; do
  if [[ -z "${!variable:-}" ]]; then
    printf 'Missing required signing secret: %s\n' "$variable" >&2
    exit 1
  fi
done
if [[ $(uname -s) != Darwin ]]; then
  printf 'Developer ID signing requires a macOS runner.\n' >&2
  exit 1
fi
if [[ "$DEVELOPER_ID_APPLICATION" != 'Developer ID Application: '* ]]; then
  printf 'DEVELOPER_ID_APPLICATION must name a Developer ID Application identity.\n' >&2
  exit 1
fi

umask 077
signing_temp=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/shistory-signing.XXXXXX")
keychain="$signing_temp/signing.keychain-db"
cleanup() {
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  rm -rf "$signing_temp"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf '%s' "$DEVELOPER_ID_CERTIFICATE_BASE64" | base64 --decode > "$signing_temp/certificate.p12"
security create-keychain -p "$KEYCHAIN_PASSWORD" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$keychain"
security import "$signing_temp/certificate.p12" -k "$keychain" \
  -P "$DEVELOPER_ID_CERTIFICATE_PASSWORD" -t cert -f pkcs12 -T /usr/bin/codesign -T /usr/bin/security
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$keychain" >/dev/null
rm "$signing_temp/certificate.p12"
xcrun notarytool store-credentials shistory-notary --keychain "$keychain" \
  --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_SPECIFIC_PASSWORD"

for arch in arm64 amd64; do
  directory="dist/shistory-darwin-$arch"
  codesign --force --sign "$DEVELOPER_ID_APPLICATION" --keychain "$keychain" \
    --identifier com.github.chr33s.shistory \
    --timestamp --options runtime "$directory/shistory"
  codesign --verify --strict --verbose=2 "$directory/shistory"
  archive="$signing_temp/shistory-darwin-$arch.zip"
  ditto -c -k --keepParent "$directory" "$archive"
  result="$signing_temp/notarization-$arch.json"
  xcrun notarytool submit "$archive" --keychain "$keychain" \
    --keychain-profile shistory-notary --wait --timeout 20m --output-format json > "$result"
  status=$(plutil -extract status raw -o - "$result")
  if [[ "$status" != Accepted ]]; then
    printf 'Apple notarization for %s was not accepted: %s\n' "$arch" "$status" >&2
    cat "$result" >&2
    exit 1
  fi
  printf 'Apple accepted notarization for %s.\n' "$arch"
done
# Standalone executables and ZIP files cannot have tickets stapled. Gatekeeper
# retrieves the ticket for the signed binary online; tar packaging preserves it.
