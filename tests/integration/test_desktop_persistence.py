import json
from pathlib import Path

from apps.desktop.persistence import persist_group
from apps.desktop.workflow import DesktopWorkflow
from packages.core import PipelineStatus, SQLiteRepository
from packages.ocr import MockOcrEngine


def test_golden_import_persists_and_exports(tmp_path: Path):
    source = Path("samples/golden/verified_wrong/screen_01.png")
    workflow = DesktopWorkflow(MockOcrEngine())
    workflow.import_paths([source], tmp_path / "imports")
    workflow.assign([0], "q001", "analysis")
    draft = workflow.recognize_group("q001")

    artifacts = persist_group(
        workflow,
        "q001",
        database=tmp_path / "study.db",
        export_root=tmp_path / "exports",
        paper_id="paper_test",
        paper_title="Golden test",
    )

    assert not draft.missing_required_fields
    assert artifacts.status is PipelineStatus.VERIFIED
    assert artifacts.database.exists() and artifacts.markdown.exists()
    payload = json.loads(artifacts.json.read_text(encoding="utf-8"))
    assert payload["questions"][0]["user_answer"] == ["B"]
    assert payload["questions"][0]["official_answer"] == ["C"]
    assert payload["questions"][0]["official_explanation_md"]
    stored = SQLiteRepository(artifacts.database).list_questions("paper_test")
    assert stored[0].evidence.analysis_frames
    assert stored[0].evidence.field_regions["official_answer"][0].bbox is not None
    assert stored[0].evidence.field_regions["official_explanation_md"][0].bbox is not None
