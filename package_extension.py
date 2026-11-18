"""Package the extension/ folder into dist/deal-hunter-extension.zip for store upload."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REQUIRED = ("manifest.json", "background.js", "popup.html", "popup.js", "popup.css",
            "options.html", "options.js", "shared.js")


def build_extension_zip(ext_dir: Path | None = None, out_zip: Path | None = None) -> Path:
    src = ext_dir or (BASE_DIR / "extension")
    dest = out_zip or (BASE_DIR / "dist" / "deal-hunter-extension.zip")
    for name in REQUIRED:
        if not (src / name).is_file():
            raise FileNotFoundError(f"Missing required extension file: {src / name}")
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 3:
        raise ValueError("manifest.json must specify manifest_version 3")

    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file() and path.name != ".DS_Store":
                zf.write(path, path.relative_to(src).as_posix())
    return dest


if __name__ == "__main__":
    out = build_extension_zip()
    print(f"Packaged extension: {out}")
