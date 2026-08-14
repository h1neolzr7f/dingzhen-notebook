from pathlib import Path

from PIL import Image

from packages.ocr import MockOcrEngine
from packages.stability import DeviceProfile, OcrDictionary, StabilityConfig, recognize_region, timed


def test_device_profile_scales_and_clamps_bbox():
    profile = DeviceProfile(name="ref")
    assert profile.scale_bbox((0, 0, 1080, 2400), 720, 1600) == (0, 0, 720, 1600)
    assert profile.scale_bbox((-5, -5, 2000, 3000), 720, 1600) == (0, 0, 720, 1600)


def test_ocr_dictionary_only_corrects_known_choice_context():
    dictionary = OcrDictionary()
    assert dictionary.correct_choice("8").corrected == "B"
    unresolved = dictionary.correct_choice("G", allowed=("A", "B", "D"))
    assert unresolved.corrected == "G" and not unresolved.changed


def test_region_recognition_writes_derived_image_and_keeps_source(tmp_path: Path):
    source = tmp_path / "raw.png"
    Image.new("RGB", (20, 20), "white").save(source)
    result = recognize_region(MockOcrEngine(), source, (2, 3, 12, 14), derived_dir=tmp_path / "derived")
    assert result.source == source
    assert result.derived_image.exists()
    assert Image.open(source).size == (20, 20)


def test_config_roundtrip_and_timing(tmp_path: Path):
    config = StabilityConfig(device_profiles=[DeviceProfile(name="ref")])
    path = config.save(tmp_path / "stability.json")
    assert StabilityConfig.load(path).device_profiles[0].name == "ref"
    value, sample = timed("unit", lambda: 2 + 2)
    assert value == 4 and sample.ok and sample.elapsed_ms >= 0

