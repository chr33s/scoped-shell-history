"""Download only the pinned fixtures for the real Zinit compatibility profile."""
import io
import json
from pathlib import Path
import tarfile
import urllib.request

root = Path(__file__).resolve().parents[1]
for repo, revision in json.loads((root / "tests/plugins.json").read_text()).items():
    destination = root / ".cache/plugins" / repo.replace("/", "---")
    if (destination / ".revision").exists() and (destination / ".revision").read_text() == revision:
        continue
    destination.mkdir(parents=True, exist_ok=True)
    url = f"https://codeload.github.com/{repo}/tar.gz/{revision}"
    print(f"Fetching {repo}@{revision}", flush=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts[1:]
            if not parts:
                continue
            member.name = str(Path(*parts))
            archive.extract(member, destination, filter="data")
    (destination / ".revision").write_text(revision)
