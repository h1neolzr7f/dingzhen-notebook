"""Generate deterministic offline fixtures for the P3-P6 regression catalog."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw


CASES = [
    ("ordinary_single_choice", "verified", "single_choice"),
    ("true_false", "verified", "true_false"),
    ("unanswered", "verified", "single_choice"),
    ("correct", "verified", "single_choice"),
    ("material_question", "verified", "single_choice"),
    ("long_stem", "verified", "single_choice"),
    ("long_explanation", "verified", "single_choice"),
    ("figure_reasoning", "verified", "single_choice"),
    ("table_analysis", "verified", "single_choice"),
    ("multi_image", "verified", "single_choice"),
    ("collapsed_explanation", "needs_review", "single_choice"),
    ("four_screen_question", "verified", "single_choice"),
    ("question_number_failure", "needs_review", "single_choice"),
    ("system_popup", "needs_review", "single_choice"),
    ("ocr_b_to_8", "needs_review", "single_choice"),
    ("ocr_c_to_g", "needs_review", "single_choice"),
]

REVIEW_REASONS = {
    "collapsed_explanation": ["missing_official_explanation"],
    "question_number_failure": ["missing_official_answer"],
    "system_popup": ["missing_official_explanation"],
    "ocr_b_to_8": ["low_ocr_confidence"],
    "ocr_c_to_g": ["missing_official_answer", "low_parse_confidence"],
}


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "samples" / "golden"
    for index, (case_id, status, question_type) in enumerate(CASES, 1):
        directory = root / case_id
        directory.mkdir(parents=True, exist_ok=True)
        image_name = "screen_01.png"
        image_path = directory / image_name
        image = Image.new("RGB", (1080, 1920), "white")
        draw = ImageDraw.Draw(image)
        draw.text((36, 80), f"Golden fixture: {case_id}", fill="black")
        draw.text((36, 260), "Synthetic offline question fixture; no real account data", fill="black")
        draw.text((36, 440), "A. Option A       B. Option B       C. Option C", fill="black")
        draw.text((36, 620), "Official answer: C", fill="black")
        draw.text((36, 800), "Official explanation: synthetic regression evidence", fill="black")
        image.save(image_path)

        evidence_path = f"samples/golden/{case_id}/{image_name}"
        official_answer = None if case_id in {"question_number_failure", "ocr_c_to_g"} else ["C"]
        explanation = None if case_id in {"collapsed_explanation", "system_popup"} else "官方解析：模拟证据"
        field_regions = {}
        if official_answer:
            field_regions["official_answer"] = [{"image": evidence_path, "bbox": [36, 600, 480, 680], "confidence": 0.99}]
        if explanation:
            field_regions["official_explanation_md"] = [{"image": evidence_path, "bbox": [36, 780, 980, 860], "confidence": 0.99}]
        expected = {
            "case_id": case_id,
            "expected_status": status,
            "expected_review_reasons": REVIEW_REASONS.get(case_id, []),
            "question": {
                "id": f"q_golden_{index:03d}",
                "paper_id": "paper_golden_catalog",
                "sequence": index,
                "question_type": question_type,
                "stem_md": "模拟题干：用于离线回归，不代表真实平台内容。",
                "options": [
                    {"label": "A", "content_md": "选项甲"},
                    {"label": "B", "content_md": "选项乙"},
                    {"label": "C", "content_md": "选项丙"},
                ],
                "user_answer": [] if case_id == "unanswered" else ["B"],
                "official_answer": official_answer,
                "official_explanation_md": explanation,
                "ocr_confidence": 0.70 if case_id == "ocr_b_to_8" else 0.99,
                "parse_confidence": 0.70 if case_id == "ocr_c_to_g" else 0.99,
                "evidence": {
                    "question_frames": [evidence_path],
                    "analysis_frames": [evidence_path],
                    "field_regions": field_regions,
                },
            },
            "notes": "Synthetic offline fixture; no real account or platform content.",
        }
        (directory / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sidecar = {
            "lines": [
                {"text": expected["question"]["stem_md"], "confidence": 0.99, "bbox": [36, 260, 980, 320]},
                {"text": "A. 选项甲  B. 选项乙  C. 选项丙", "confidence": 0.99, "bbox": [36, 440, 980, 500]},
                {"text": "用户答案：B", "confidence": 0.70 if case_id == "ocr_b_to_8" else 0.99, "bbox": [36, 560, 600, 620]},
                {"text": "正确答案：C", "confidence": 0.70 if case_id == "ocr_c_to_g" else 0.99, "bbox": [36, 620, 600, 680]},
                {"text": "官方解析：模拟证据", "confidence": 0.99, "bbox": [36, 800, 980, 860]},
            ]
        }
        (directory / f"{image_name}.ocr.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog = []
    for expected_path in sorted(root.glob("*/expected.json")):
        case_dir = expected_path.parent
        catalog.append(
            {
                "case_id": case_dir.name,
                "expected": str(expected_path.relative_to(root)),
                "image_count": len(list(case_dir.glob("*.png"))),
            }
        )
    (root / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
