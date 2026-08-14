"""Windows desktop and CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Sequence

from packages.core.models import Paper, Question
from packages.core.version import __version__
from packages.ocr import PaddleOcrUnavailable, create_ocr_engine
from packages.paper_builder import build_paper_bundle
from packages.stability import download_update, fetch_update_manifest, update_available

from .capture_controller import AdbCaptureService, CaptureController, CaptureStatus
from .ai_workflow import run_ai_analysis
from .persistence import persist_group
from .pipeline import process_capture_frames
from .workflow import DesktopWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="粉笔学习截图导入、校对、采集与组卷工具")
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "capture",
            "capture-paper",
            "build-paper",
            "ai-analyze",
            "check-update",
            "export-mistake-package",
            "import-mistake-package",
            "review-plan",
            "receive-lan",
        ),
        help=(
            "capture=仅保存 ADB 原始帧；capture-paper=采集后自动 OCR/入库/分析/组卷；"
            "export/import-mistake-package=今知兼容错题包；review-plan=预习/一刷/二刷复习计划；"
            "receive-lan=接收手机无线传入并自动识别"
        ),
    )
    parser.add_argument("--cli", action="store_true", help="无 GUI 模式")
    parser.add_argument("--ocr-engine", choices=("mock", "paddle"), default="paddle")
    parser.add_argument("--import", dest="imports", nargs="*", default=[], metavar="PATH")
    parser.add_argument("--group", default="q001")
    parser.add_argument("--kind", choices=("question", "analysis", "unassigned"), default="unassigned")
    parser.add_argument("--output", type=Path, default=Path("exports") / "ocr-draft.json")
    parser.add_argument("--database", type=Path, default=Path("data") / "fenbi-study.db")
    parser.add_argument("--paper-id", default="paper_manual_import")
    parser.add_argument("--paper-title", default="手工截图导入试卷")
    parser.add_argument("--device", help="ADB 设备序列号；未提供时使用首个已授权设备")
    parser.add_argument("--capture-output", type=Path, default=Path("data") / "captures")
    parser.add_argument("--max-frames", type=int, default=-1, help="最多保存帧数；-1 表示持续到停止")
    parser.add_argument("--capture-interval", type=float, default=0.0)
    parser.add_argument("--swipe-after-frame", action="store_true")
    parser.add_argument("--paper-json", type=Path, help="build-paper 使用的 JSON 交换文件")
    parser.add_argument("--paper-output", type=Path, default=Path("exports") / "paper_bundle")
    parser.add_argument("--paper-formats", nargs="+", choices=("pdf", "html"), default=("pdf", "html"))
    parser.add_argument("--ai-endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--ai-model", default="local")
    parser.add_argument("--update-config", type=Path, default=Path("config") / "update.json")
    parser.add_argument("--download-update", action="store_true", help="发现新版本后下载经 SHA-256 校验的安装包")
    parser.add_argument(
        "--package-zip",
        type=Path,
        default=Path("exports") / "mistake-package.zip",
        help="今知兼容错题包 ZIP 路径",
    )
    parser.add_argument(
        "--package-media-root",
        type=Path,
        action="append",
        default=[],
        help="导出错题包时搜索截图/媒体的目录，可重复",
    )
    parser.add_argument(
        "--include-correct",
        action="store_true",
        help="导出错题包时包含作答正确的题目",
    )
    parser.add_argument(
        "--review-json",
        type=Path,
        default=Path("exports") / "review-plan.json",
        help="复习计划 JSON 输出",
    )
    parser.add_argument(
        "--review-md",
        type=Path,
        default=Path("exports") / "review-plan.md",
        help="复习计划 Markdown 输出",
    )
    parser.add_argument(
        "--mindmap-md",
        type=Path,
        default=Path("exports") / "knowledge-mindmap.md",
        help="知识点导图 Markdown 输出",
    )
    parser.add_argument("--lan-port", type=int, default=17831, help="手机无线接收端口")
    parser.add_argument("--lan-secret", help="无线配对密钥；省略则自动生成")
    parser.add_argument("--lan-timeout", type=int, default=3600, help="等待手机传入的秒数")
    return parser


def cli_main(args: argparse.Namespace) -> int:
    if not args.imports:
        print("CLI 模式需要至少一个 --import PATH。", file=sys.stderr)
        return 2
    try:
        engine = create_ocr_engine(args.ocr_engine)
    except PaddleOcrUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2
    workflow = DesktopWorkflow(engine)
    images = workflow.import_paths(args.imports, Path("data") / "imports")
    if not images:
        print("没有找到支持的图片文件。", file=sys.stderr)
        return 2
    workflow.assign(range(len(images)), args.group, args.kind)
    draft = workflow.recognize_group(args.group)
    workflow.save_draft(args.group, args.output)
    artifacts = persist_group(
        workflow,
        args.group,
        database=args.database,
        paper_id=args.paper_id,
        paper_title=args.paper_title,
    )
    print(
        json.dumps(
            {
                "draft": str(args.output),
                "database": str(artifacts.database),
                "json": str(artifacts.json),
                "markdown": str(artifacts.markdown),
                "images": len(images),
                "status": artifacts.status.value,
                "missing": draft.missing_required_fields,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cli_capture(args: argparse.Namespace, *, process_after_capture: bool = False) -> int:
    """Run the P2 capture controller without starting the Qt event loop."""

    max_frames = None if args.max_frames < 0 else args.max_frames
    service = AdbCaptureService(
        output_dir=args.capture_output,
        serial=args.device,
        max_frames=max_frames,
        interval_seconds=args.capture_interval,
        swipe_after_frame=args.swipe_after_frame,
    )
    controller = CaptureController(service, output_dir=args.capture_output)
    snapshot = controller.start(wait=True)
    payload = {
        "status": snapshot.status.value,
        "message": snapshot.message,
        "error": snapshot.error,
        "device": snapshot.device or args.device,
        "frames_captured": snapshot.frames_captured,
        "output_dir": str(args.capture_output),
        "frames": [str(frame.path) for frame in controller.frames if frame.path],
    }
    if snapshot.status is CaptureStatus.NO_DEVICE:
        print(json.dumps(payload, ensure_ascii=False))
        print("未检测到可用 Android 设备；请连接并授权 USB 调试。", file=sys.stderr)
        return 3
    if snapshot.status is CaptureStatus.ERROR:
        print(json.dumps(payload, ensure_ascii=False))
        return 1
    if process_after_capture:
        try:
            engine = create_ocr_engine(args.ocr_engine)
            processed = process_capture_frames(
                [frame.path for frame in controller.frames if frame.path],
                engine=engine,
                workspace=Path.cwd(),
                database=args.database,
                paper_id=args.paper_id,
                paper_title=args.paper_title,
            )
            payload["processing"] = {
                "questions": processed.questions,
                "review_count": processed.review_count,
                "database": str(processed.database),
                "paper_json": str(processed.paper_json),
                "paper_markdown": str(processed.paper_markdown),
                "analysis_markdown": str(processed.analysis_markdown),
                "paper_bundle": str(processed.paper_bundle),
            }
        except (PaddleOcrUnavailable, OSError, RuntimeError, ValueError) as exc:
            payload["processing_error"] = str(exc)
            print(json.dumps(payload, ensure_ascii=False))
            return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cli_build_paper(args: argparse.Namespace) -> int:
    if args.paper_json is None:
        print("build-paper 需要 --paper-json paper.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(args.paper_json.read_text(encoding="utf-8"))
        paper = Paper.model_validate(document["paper"])
        questions = [Question.model_validate(item) for item in document.get("questions", [])]
        result = build_paper_bundle(paper, questions, args.paper_output, formats=args.paper_formats)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"组卷失败: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "paper_id": paper.id,
                "questions": len(questions),
                "output": str(args.paper_output),
                "paths": [str(path) for path in result.paths()],
                "formats": list(args.paper_formats),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cli_ai_analyze(args: argparse.Namespace) -> int:
    try:
        result = run_ai_analysis(
            args.database,
            args.paper_id,
            output_root=Path.cwd() / "exports",
            endpoint=args.ai_endpoint,
            model=args.ai_model,
        )
    except (OSError, KeyError, RuntimeError, ValueError) as exc:
        print(f"AI 分析失败: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "model": result.model,
                "questions": result.questions_analyzed,
                "needs_review": result.needs_review,
                "json": str(result.json_path),
                "markdown": str(result.markdown_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cli_export_mistake_package(args: argparse.Namespace) -> int:
    """Export Fenbi paper JSON into a 今知兼容 jinzhi-mistake-package ZIP."""

    from packages.mistake_package import export_mistake_package

    if args.paper_json is None:
        print("export-mistake-package 需要 --paper-json paper.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(args.paper_json.read_text(encoding="utf-8"))
        paper = Paper.model_validate(document["paper"])
        questions = [Question.model_validate(item) for item in document.get("questions", [])]
        media_roots = list(args.package_media_root) or [
            Path("data"),
            Path("exports"),
            Path("samples"),
        ]
        path = export_mistake_package(
            paper,
            questions,
            args.package_zip,
            media_roots=media_roots,
            only_wrong=not args.include_correct,
            title=args.paper_title or paper.title,
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"导出错题包失败: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "package_zip": str(path),
                "format": "jinzhi-mistake-package",
                "schema_version": 1,
                "paper_id": paper.id,
                "questions": len(questions),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cli_import_mistake_package(args: argparse.Namespace) -> int:
    """Import a 今知兼容 ZIP into local paper JSON + optional media."""

    from packages.core.repository import SQLiteRepository
    from packages.exporters.json_exporter import export_paper_json
    from packages.exporters.markdown_exporter import export_paper_markdown
    from packages.mistake_package import import_mistake_package

    if not args.package_zip.is_file():
        print(f"找不到错题包: {args.package_zip}", file=sys.stderr)
        return 2
    try:
        media_dir = Path("data") / "imports" / "mistake-package-media"
        paper, questions, _ = import_mistake_package(
            args.package_zip,
            extract_media_to=media_dir,
            paper_id=args.paper_id if args.paper_id != "paper_manual_import" else None,
        )
        out_dir = Path("exports") / paper.id
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = export_paper_json(paper, questions, out_dir / "paper.json")
        md_path = export_paper_markdown(paper, questions, out_dir / "paper_ai.md")
        repo = SQLiteRepository(args.database)
        repo.create_schema()
        repo.upsert_paper(paper)
        for question in questions:
            repo.upsert_question(question)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"导入错题包失败: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "paper_id": paper.id,
                "title": paper.title,
                "questions": len(questions),
                "json": str(json_path),
                "markdown": str(md_path),
                "database": str(args.database),
                "media_dir": str(media_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cli_review_plan(args: argparse.Namespace) -> int:
    """Build 预习/一刷/二刷/间隔复习 plan and knowledge mind-map."""

    from packages.review.scheduler import (
        build_review_plan,
        export_knowledge_mindmap,
        write_review_plan,
    )

    if args.paper_json is None:
        print("review-plan 需要 --paper-json paper.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(args.paper_json.read_text(encoding="utf-8"))
        questions = [Question.model_validate(item) for item in document.get("questions", [])]
        plan = build_review_plan(questions)
        json_path, md_path = write_review_plan(plan, args.review_json, args.review_md)
        mindmap = export_knowledge_mindmap(questions, args.mindmap_md)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"复习计划生成失败: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "review_json": str(json_path),
                "review_md": str(md_path) if md_path else None,
                "mindmap_md": str(mindmap),
                "summary": plan.get("summary"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cli_receive_lan(args: argparse.Namespace) -> int:
    from packages.capture import LanReceiveServer
    from packages.core import new_paper_id

    done = threading.Event()
    received: list[Path] = []

    def on_complete(_task_id: str, paths: list[Path]) -> None:
        received.extend(paths)
        done.set()

    paper_id = args.paper_id if args.paper_id != "paper_manual_import" else new_paper_id("paper")
    inbox = Path("data") / "lan_inbox" / paper_id
    server = LanReceiveServer(
        inbox,
        secret=args.lan_secret,
        port=args.lan_port,
        on_complete=on_complete,
    )
    server.start()
    print(
        json.dumps(
            {
                "version": __version__,
                "paper_id": paper_id,
                "port": server.actual_port,
                "pairing": server.pairing_codes(),
            },
            ensure_ascii=False,
        )
    )
    sys.stdout.flush()
    finished = done.wait(timeout=max(1, args.lan_timeout))
    server.stop()
    if not finished:
        print("等待手机传入超时。", file=sys.stderr)
        return 2
    if not received:
        print("没有收到截图。", file=sys.stderr)
        return 2
    try:
        engine = create_ocr_engine(args.ocr_engine)
    except PaddleOcrUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2
    processed = process_capture_frames(
        received,
        engine=engine,
        workspace=Path.cwd(),
        database=args.database,
        paper_id=paper_id,
        paper_title=args.paper_title or "无线传入试卷",
    )
    print(
        json.dumps(
            {
                "paper_id": paper_id,
                "questions": processed.questions,
                "review_count": processed.review_count,
                "paper_markdown": str(processed.paper_markdown),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cli_check_update(args: argparse.Namespace) -> int:
    try:
        config = json.loads(args.update_config.read_text(encoding="utf-8"))
        manifest_url = str(config.get("manifest_url", "")).strip()
        current_version = str(config.get("current_version", "1.0.0"))
        if not manifest_url:
            print(json.dumps({"configured": False, "current_version": current_version}, ensure_ascii=False))
            return 0
        manifest = fetch_update_manifest(manifest_url)
        available = update_available(current_version, manifest)
        payload = {
            "configured": True,
            "current_version": current_version,
            "latest_version": manifest.version,
            "available": available,
            "release_notes": manifest.release_notes,
        }
        if available and args.download_update:
            destination = Path("data") / "updates" / f"FenbiStudy-{manifest.version}-Setup.exe"
            payload["installer"] = str(download_update(manifest, destination))
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"更新检查失败: {exc}", file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "capture":
        return cli_capture(args)
    if args.command == "capture-paper":
        return cli_capture(args, process_after_capture=True)
    if args.command == "build-paper":
        return cli_build_paper(args)
    if args.command == "ai-analyze":
        return cli_ai_analyze(args)
    if args.command == "check-update":
        return cli_check_update(args)
    if args.command == "export-mistake-package":
        return cli_export_mistake_package(args)
    if args.command == "import-mistake-package":
        return cli_import_mistake_package(args)
    if args.command == "review-plan":
        return cli_review_plan(args)
    if args.command == "receive-lan":
        return cli_receive_lan(args)
    if args.cli:
        return cli_main(args)
    try:
        from .gui import run_gui
    except ImportError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            print("PySide6 未安装；请安装项目依赖或使用 --cli。", file=sys.stderr)
            return 2
        raise
    return run_gui(args.ocr_engine)


if __name__ == "__main__":
    raise SystemExit(main())
