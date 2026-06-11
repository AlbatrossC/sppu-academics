import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DIST_DIR = STATIC_DIR / "dist"
MANIFEST_PATH = STATIC_DIR / "asset-manifest.json"

ASSETS = [
    "css/viewer.css",
    "css/select.css",
    "css/header.css",
    "css/footer.css",
    "js/analytics.js",
    "js/select.js",
    "js/mobile-menu.js",
    "js/download-paper.js",
]


def minify_css(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"\s+", " ", source)
    source = re.sub(r"\s*([{}:;,>~])\s*", r"\1", source)
    source = source.replace(";}", "}")
    return source.strip()


def minify_js(source):
    try:
        import rjsmin

        return rjsmin.jsmin(source).strip()
    except ImportError:
        pass

    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def build_asset(relative_name):
    source_path = STATIC_DIR / relative_name
    source = source_path.read_text(encoding="utf-8")
    suffix = source_path.suffix

    if suffix == ".css":
        output = minify_css(source)
    elif suffix == ".js":
        output = minify_js(source)
    else:
        output = source

    digest = hashlib.sha256(output.encode("utf-8")).hexdigest()[:10]
    output_name = f"{source_path.stem}.{digest}{suffix}"
    output_relative = Path("dist") / source_path.parent.relative_to(STATIC_DIR) / output_name
    output_path = STATIC_DIR / output_relative
    
    return relative_name, output_relative.as_posix(), output_path, output


def main():
    old_manifest = {}
    if MANIFEST_PATH.exists():
        try:
            old_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    new_manifest = {}
    assets_data = []

    for asset in ASSETS:
        source, output_rel, output_path, output_content = build_asset(asset)
        new_manifest[source] = output_rel
        assets_data.append((source, output_rel, output_path, output_content))

    if new_manifest == old_manifest:
        print("\033[91mNo changes detected.\033[0m")
        return

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)

    print("\033[92mChanges detected! New files created:\033[0m")
    for source, output_rel, output_path, output_content in assets_data:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_content + "\n", encoding="utf-8")
        
        if old_manifest.get(source) != output_rel:
            print(f"\033[92m  {source} -> {output_rel}\033[0m")
        else:
            print(f"  {source} -> {output_rel}")

    MANIFEST_PATH.write_text(
        json.dumps(new_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
