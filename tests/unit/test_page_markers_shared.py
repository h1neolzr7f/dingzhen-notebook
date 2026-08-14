import json
from pathlib import Path

from packages.core import __version__
from packages.ocr import load_page_markers


ROOT = Path(__file__).parents[2]


def test_product_version_is_aligned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    update = json.loads((ROOT / "config" / "update.json").read_text(encoding="utf-8"))
    gradle = (ROOT / "apps" / "android-capture" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in pyproject
    assert update["current_version"] == __version__
    assert f'versionName = "{__version__}"' in gradle
    assert "versionCode = 10304" in gradle


def test_android_and_python_share_page_markers() -> None:
    config = json.loads((ROOT / "config" / "page_markers.json").read_text(encoding="utf-8"))
    assets = json.loads(
        (ROOT / "apps" / "android-capture" / "app" / "src" / "main" / "assets" / "page_markers.json").read_text(
            encoding="utf-8"
        )
    )
    assert config == assets
    loaded = load_page_markers()
    kotlin = (
        ROOT
        / "apps"
        / "android-capture"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "local"
        / "fenbistudy"
        / "capture"
        / "FenbiPageClassifier.kt"
    ).read_text(encoding="utf-8")
    for key in ("user_answer", "official_answer", "explanation", "end_markers", "paper_end", "skip"):
        for marker in config[key]:
            assert marker in kotlin
            assert marker in loaded[key]
