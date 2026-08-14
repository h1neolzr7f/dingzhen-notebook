import json
from pathlib import Path

from apps.desktop.main import main


def test_build_paper_cli_generates_all_printables(tmp_path: Path, capsys) -> None:
    source = json.loads((Path("exports") / "paper_smoke" / "paper.json").read_text(encoding="utf-8"))
    paper_json = tmp_path / "paper.json"
    paper_json.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    destination = tmp_path / "bundle"
    assert main(
        [
            "build-paper",
            "--paper-json",
            str(paper_json),
            "--paper-output",
            str(destination),
            "--paper-formats",
            "pdf",
            "html",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["questions"] == 1
    assert (destination / "01_wrong_paper.pdf").is_file()
    assert (destination / "03_explanation_book.html").is_file()
