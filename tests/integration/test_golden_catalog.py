import json
from pathlib import Path


def test_full_golden_catalog_has_expected_json_and_images():
    root = Path("samples/golden")
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog) >= 16
    for item in catalog:
        directory = root / Path(item["expected"]).parent
        expected = directory / "expected.json"
        images = list(directory.glob("*.png"))
        assert expected.exists(), item["case_id"]
        assert images, item["case_id"]
        payload = json.loads(expected.read_text(encoding="utf-8"))
        assert payload["case_id"] == item["case_id"]

