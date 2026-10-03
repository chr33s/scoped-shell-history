#!/usr/bin/env bash
set -euo pipefail
: "${GITHUB_SHA:?GITHUB_SHA must identify the tested commit}"
: "${GH_REPO:?GH_REPO must identify the release repository}"
: "${GH_TOKEN:?GH_TOKEN is required to publish releases}"

tag="main-$GITHUB_SHA"
assets=(
  dist/shistory-darwin-arm64.tar.gz
  dist/shistory-darwin-amd64.tar.gz
  dist/shistory-linux-amd64.tar.gz
  dist/shistory-linux-arm64.tar.gz
  dist/SHA256SUMS
)
for asset in "${assets[@]}"; do
  test -s "$asset"
done

# Published releases stay unchanged on reruns; interrupted drafts can resume.
if draft=$(gh release view "$tag" --json isDraft --jq '.isDraft'); then
  if [[ "$draft" == false ]]; then
    printf 'Release %s is already published.\n' "$tag"
    exit 0
  fi
else
  notes=$(mktemp)
  trap 'rm -f "$notes"' EXIT
  cat > "$notes" <<EOF
Built from commit [$GITHUB_SHA](https://github.com/$GH_REPO/commit/$GITHUB_SHA) after Linux and macOS checks passed.

Downloads include the shistory binary, Bash/Zsh adapters, Zsh completions, README, and license. Verify archives against SHA256SUMS.

macOS binaries are Developer ID signed and notarized by Apple. Standalone binaries require an online Gatekeeper check because notarization tickets cannot be stapled to them.
EOF
  gh release create "$tag" --draft --target "$GITHUB_SHA" \
    --title "main ${GITHUB_SHA:0:12}" --notes-file "$notes"
fi

# Publish only after all assets upload successfully.
gh release upload "$tag" "${assets[@]}" --clobber
gh release edit "$tag" --draft=false
