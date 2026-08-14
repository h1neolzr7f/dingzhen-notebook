from __future__ import annotations

from packages.ai import AnalysisKind, PromptRegistry, build_prompt, split_question_payload


def test_prompt_separates_read_only_official_source_from_ai_context() -> None:
    prompt = build_prompt(
        AnalysisKind.QUESTION_ERROR,
        official_source={"official_answer": ["C"], "official_explanation_md": "因为条件..."},
        user_and_history={"user_answer": ["B"], "duration_seconds": 83},
    )
    assert "OFFICIAL_SOURCE (READ ONLY" in prompt
    assert '"official_answer": [' in prompt
    assert '"user_answer": [' in prompt
    assert "Never change" in prompt
    assert "Return one JSON object" in prompt


def test_split_question_payload_keeps_official_values_out_of_context() -> None:
    official, context = split_question_payload(
        {
            "official_answer": ["C"],
            "official_explanation_md": "official",
            "stem_md": "stem",
            "user_answer": ["B"],
        }
    )
    assert official == {"official_answer": ["C"], "official_explanation_md": "official"}
    assert context == {"stem_md": "stem", "user_answer": ["B"]}


def test_prompt_version_changes_cache_namespace() -> None:
    first = PromptRegistry(version="p5.v1")
    second = PromptRegistry(version="p5.v2")
    assert first.version_for(AnalysisKind.PAPER) != second.version_for(AnalysisKind.PAPER)

