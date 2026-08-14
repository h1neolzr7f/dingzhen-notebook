from PIL import Image

from packages.image_processing import assign_group, import_images, scan_images


def _image(path, color):
    Image.new("RGB", (16, 24), color).save(path)


def test_import_is_natural_sorted_and_content_deduplicated(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _image(source / "shot10.png", "red")
    _image(source / "shot2.png", "blue")
    (source / "shot2-copy.png").write_bytes((source / "shot2.png").read_bytes())

    imported = import_images([source], tmp_path / "session")

    assert len(imported) == 2
    assert [item.source_path.name for item in imported] == ["shot2-copy.png", "shot10.png"]
    assert all(item.path.parent.name == "raw" for item in imported)
    assert all(item.width == 16 and item.height == 24 for item in imported)
    assert (source / "shot2.png").exists()


def test_assign_group_is_non_mutating(tmp_path):
    first = tmp_path / "1.png"
    second = tmp_path / "2.png"
    _image(first, "white")
    _image(second, "black")
    images = import_images([first, second])

    grouped = assign_group(images, [0], "q001", "question")

    assert images[0].group_id == "unassigned"
    assert grouped[0].group_id == "q001"
    assert grouped[0].page_kind == "question"
    assert grouped[1].group_id == "unassigned"


def test_scan_images_ignores_unsupported_files(tmp_path):
    _image(tmp_path / "a.png", "white")
    (tmp_path / "notes.txt").write_text("not an image", encoding="utf-8")
    assert [item.name for item in scan_images([tmp_path])] == ["a.png"]


def test_import_preserves_mock_ocr_sidecar(tmp_path):
    source = tmp_path / "screen.png"
    _image(source, "white")
    sidecar = tmp_path / "screen.png.ocr.json"
    sidecar.write_text('{"lines": [{"text": "正确答案：C"}]}', encoding="utf-8")

    imported = import_images([source], tmp_path / "session")

    copied = imported[0].path.with_name(imported[0].path.name + ".ocr.json")
    assert copied.read_text(encoding="utf-8") == sidecar.read_text(encoding="utf-8")
