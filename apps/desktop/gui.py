"""Beginner-friendly PySide6 review UI: collect → review → export."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from packages.capture import LanReceiveServer
from packages.core import SQLiteRepository, __version__, new_paper_id
from packages.mistake_package import export_mistake_package
from packages.ocr import FieldEvidence, MockOcrEngine, PaddleOcrUnavailable, create_ocr_engine
from packages.review.scheduler import build_review_plan, export_knowledge_mindmap, write_review_plan

from .ai_workflow import run_ai_analysis
from .capture_controller import AdbCaptureService, CaptureController, CaptureFrame, CaptureSnapshot, CaptureStatus
from .persistence import persist_group
from .pipeline import classify_and_persist, process_capture_frames, rebuild_paper_outputs
from .workflow import DesktopWorkflow

_KIND_LABELS = {"question": "题目页", "analysis": "解析页", "unassigned": "未标记"}
_KIND_VALUES = {label: key for key, label in _KIND_LABELS.items()}
_ENGINE_LABELS = {"mock": "试用识别（不用下载）", "paddle": "精确识别（首次需下载）"}


class _WorkerBridge(QObject):
    finished = Signal(object)
    ai_finished = Signal(object)
    lan_progress = Signal(object)
    lan_complete = Signal(object)


class ChoiceChips(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.buttons: list[QToolButton] = []
        self.unanswered = QToolButton()
        self.unanswered.setText("未作答")
        self.unanswered.setCheckable(True)
        self.unanswered.clicked.connect(self._clear_choices)
        for label in "ABCDEFGH":
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False: self.unanswered.setChecked(False))
            layout.addWidget(button)
            self.buttons.append(button)
        layout.addWidget(self.unanswered)
        layout.addStretch()

    def _clear_choices(self) -> None:
        if self.unanswered.isChecked():
            for button in self.buttons:
                button.setChecked(False)

    def set_answers(self, values: list[str] | None) -> None:
        selected = set(values or [])
        self.unanswered.setChecked(values == [])
        for button in self.buttons:
            button.setChecked(button.text() in selected)

    def answers(self) -> list[str] | None:
        if self.unanswered.isChecked():
            return []
        chosen = [button.text() for button in self.buttons if button.isChecked()]
        return chosen or None


class MainWindow(QMainWindow):
    def __init__(self, engine_name: str = "mock", capture_service=None) -> None:
        super().__init__()
        self.setWindowTitle(f"粉笔学习整理 {__version__}")
        self.resize(1280, 840)
        self.engine_name = engine_name if engine_name in _ENGINE_LABELS else "mock"
        self.workflow = DesktopWorkflow(MockOcrEngine())
        self.database = Path.cwd() / "data" / "fenbi-study.db"
        self.export_root = Path.cwd() / "exports"
        self.paper_id = new_paper_id("paper")
        self.paper_title = "新试卷"
        self.group_ids: list[str] = []
        self.review_index = 0
        self._capture_frame_paths: list[Path] = []
        self._capture_generation = 0
        self._processed_generation = -1
        self._lan_server: LanReceiveServer | None = None
        self._worker_bridge = _WorkerBridge()
        self._worker_bridge.finished.connect(self._pipeline_finished)
        self._worker_bridge.ai_finished.connect(self._ai_finished)
        self._worker_bridge.lan_progress.connect(self._lan_progress)
        self._worker_bridge.lan_complete.connect(self._lan_complete)
        service = capture_service or AdbCaptureService(
            output_dir=Path.cwd() / "data" / "captures",
            max_frames=None,
            interval_seconds=0.45,
            swipe_after_frame=True,
        )
        self.capture_controller = CaptureController(
            service,
            output_dir=Path.cwd() / "data" / "captures",
            on_status=self._capture_status_changed,
            on_frame=self._capture_frame_received,
        )
        self._build_ui()
        self._switch_engine(self.engine_name)
        self._refresh_recent()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        self.step_label = QLabel("收题 → 校对 → 导出")
        header.addWidget(self.step_label)
        header.addStretch()
        header.addWidget(QLabel("识别方式"))
        self.engine_combo = QComboBox()
        for key, label in _ENGINE_LABELS.items():
            self.engine_combo.addItem(label, key)
        self.engine_combo.setCurrentIndex(0 if self.engine_name == "mock" else 1)
        self.engine_combo.currentIndexChanged.connect(self._engine_changed)
        header.addWidget(self.engine_combo)
        layout.addLayout(header)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._home_page())
        self.pages.addWidget(self._collect_page())
        self.pages.addWidget(self._review_page())
        self.pages.addWidget(self._results_page())
        layout.addWidget(self.pages, 1)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.setCentralWidget(root)
        self.statusBar().showMessage("本软件不登录粉笔。导入截图，或在已经登录的粉笔里采集。")

    def _home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("把已完成的粉笔试卷，整理成错题本")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(QLabel("本软件不登录粉笔，也不要账号密码。只整理你在已经登录的粉笔里能看到的已完成试卷。"))
        buttons = QHBoxLayout()
        import_btn = QPushButton("1. 导入截图")
        import_btn.clicked.connect(self._start_import)
        capture_btn = QPushButton("2. 手机自动采集")
        capture_btn.clicked.connect(self._show_collect)
        lan_btn = QPushButton("3. 手机无线传入")
        lan_btn.clicked.connect(self._show_lan_receive)
        open_btn = QPushButton("4. 打开已有试卷")
        open_btn.clicked.connect(lambda: self._open_selected_paper(force=True))
        for button in (import_btn, capture_btn, lan_btn, open_btn):
            button.setMinimumHeight(48)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("最近试卷"))
        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(lambda _: self._open_selected_paper(force=True))
        layout.addWidget(self.recent_list, 1)
        return page

    def _collect_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("收题：导入截图，或对着已经打开的粉笔试卷自动拍。本软件不登录粉笔。"))
        row = QHBoxLayout()
        import_button = QPushButton("导入截图")
        import_button.clicked.connect(self._import_files)
        self.capture_start_button = QPushButton("开始自动采集")
        self.capture_pause_button = QPushButton("暂停")
        self.capture_resume_button = QPushButton("继续")
        self.capture_stop_button = QPushButton("停止")
        self.capture_process_button = QPushButton("整理已拍截图")
        self.capture_process_button.setEnabled(False)
        self.capture_pause_button.setEnabled(False)
        self.capture_resume_button.setEnabled(False)
        self.capture_stop_button.setEnabled(False)
        self.capture_start_button.clicked.connect(self._start_capture)
        self.capture_pause_button.clicked.connect(self._pause_capture)
        self.capture_resume_button.clicked.connect(self._resume_capture)
        self.capture_stop_button.clicked.connect(self._stop_capture)
        self.capture_process_button.clicked.connect(self._confirm_process_frames)
        self.lan_start_button = QPushButton("手机无线传入")
        self.lan_stop_button = QPushButton("停止接收")
        self.lan_stop_button.setEnabled(False)
        self.lan_start_button.clicked.connect(self._start_lan_receive)
        self.lan_stop_button.clicked.connect(self._stop_lan_receive)
        for widget in (
            import_button,
            self.capture_start_button,
            self.capture_pause_button,
            self.capture_resume_button,
            self.capture_stop_button,
            self.capture_process_button,
            self.lan_start_button,
            self.lan_stop_button,
        ):
            row.addWidget(widget)
        layout.addLayout(row)
        self.capture_status_label = QLabel("采集空闲。请在已经登录的粉笔里打开已完成试卷。")
        self.lan_code_label = QLabel("")
        self.lan_code_label.setWordWrap(True)
        self.lan_code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.capture_status_label)
        layout.addWidget(self.lan_code_label)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["顺序", "截图", "第几题", "页面"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._preview_selected)
        layout.addWidget(self.table, 1)
        mid = QHBoxLayout()
        self.preview = QLabel("把题目页和解析页都导进来")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(280, 360)
        mid.addWidget(self.preview, 1)
        side = QVBoxLayout()
        self.group_edit = QLineEdit("q001")
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["题目页", "解析页", "未标记"])
        assign_button = QPushButton("把所选截图标到这题")
        assign_button.clicked.connect(self._assign_selected)
        auto_button = QPushButton("自动分题并开始校对")
        auto_button.clicked.connect(self._auto_group_and_review)
        back = QPushButton("返回首页")
        back.clicked.connect(lambda: self._goto(0, "收题 → 校对 → 导出"))
        side.addWidget(QLabel("题号，例如 q001"))
        side.addWidget(self.group_edit)
        side.addWidget(self.kind_combo)
        side.addWidget(assign_button)
        side.addWidget(auto_button)
        side.addStretch()
        side.addWidget(back)
        mid.addLayout(side)
        layout.addLayout(mid, 1)
        return page

    def _review_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        left = QVBoxLayout()
        self.review_progress = QLabel("第 1 题")
        self.review_preview = QLabel("还没有截图")
        self.review_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.review_preview.setMinimumSize(360, 480)
        left.addWidget(self.review_progress)
        left.addWidget(self.review_preview, 1)
        layout.addLayout(left, 1)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        self.stem_edit = QTextEdit()
        self.options_edit = QTextEdit()
        self.user_chips = ChoiceChips()
        self.official_chips = ChoiceChips()
        self.explanation_edit = QTextEdit()
        self.status_label = QLabel("尚未识别")
        form.addRow("题干", self.stem_edit)
        form.addRow("选项（每行 A. 内容）", self.options_edit)
        form.addRow("我的答案", self.user_chips)
        form.addRow("粉笔正确答案", self.official_chips)
        form.addRow("粉笔官方解析", self.explanation_edit)
        form.addRow("还缺什么", self.status_label)
        nav = QHBoxLayout()
        prev_btn = QPushButton("上一题")
        next_btn = QPushButton("保存并下一题")
        done_btn = QPushButton("完成校对，去导出")
        prev_btn.clicked.connect(lambda: self._step_review(-1))
        next_btn.clicked.connect(lambda: self._step_review(1))
        done_btn.clicked.connect(self._finish_review)
        nav.addWidget(prev_btn)
        nav.addWidget(next_btn)
        nav.addWidget(done_btn)
        form.addRow(nav)
        layout.addWidget(form_widget, 1)
        return page

    def _results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.results_label = QLabel("还没有生成结果")
        self.results_label.setWordWrap(True)
        layout.addWidget(self.results_label)
        row = QHBoxLayout()
        build_btn = QPushButton("生成错题卷和解析册")
        build_btn.clicked.connect(self._build_current_paper)
        pack_btn = QPushButton("导出错题包")
        pack_btn.clicked.connect(self._export_package)
        review_btn = QPushButton("生成本周复习")
        review_btn.clicked.connect(self._export_review)
        ai_btn = QPushButton("本机 AI 分析（可选）")
        ai_btn.clicked.connect(self._run_ai_analysis)
        folder_btn = QPushButton("打开导出文件夹")
        folder_btn.clicked.connect(self._open_export_folder)
        home_btn = QPushButton("回首页")
        home_btn.clicked.connect(lambda: self._goto(0, "收题 → 校对 → 导出"))
        for button in (build_btn, pack_btn, review_btn, ai_btn, folder_btn, home_btn):
            row.addWidget(button)
        layout.addLayout(row)
        layout.addStretch()
        return page

    def _goto(self, index: int, step: str) -> None:
        self.pages.setCurrentIndex(index)
        self.step_label.setText(step)

    def _show_collect(self) -> None:
        self._new_paper("采集试卷")
        self._goto(1, "正在收题")
        QMessageBox.information(
            self,
            "自动采集",
            "本软件不登录粉笔。请先在粉笔官方 App 里打开一套已完成、带解析的试卷。\n"
            "点「开始自动采集」后会一直拍到本卷结束，然后自动识别并进入校对。\n"
            "同一 Wi-Fi 也可点「手机无线传入」，把配对码贴到手机伴侣。",
        )

    def _show_lan_receive(self) -> None:
        self._stop_lan_receive()
        self._new_paper("无线传入试卷")
        self._goto(1, "正在收题")
        self._start_lan_receive()

    def _start_lan_receive(self) -> None:
        if self._lan_server is not None:
            return
        inbox = Path.cwd() / "data" / "lan_inbox" / self.paper_id
        server = LanReceiveServer(
            inbox,
            on_frame=lambda task_id, path, sequence: self._worker_bridge.lan_progress.emit(
                (task_id, path, sequence)
            ),
            on_complete=lambda task_id, paths: self._worker_bridge.lan_complete.emit((task_id, paths)),
        )
        try:
            server.start()
        except OSError as exc:
            QMessageBox.critical(self, "无法接收", f"打不开接收端口：{exc}")
            return
        self._lan_server = server
        codes = "\n".join(server.pairing_codes())
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and server.pairing_codes():
            clipboard.setText(server.pairing_codes()[0])
        self.lan_code_label.setText(
            "手机伴侣粘贴配对码（已复制第一条）：\n" + codes + "\n同一 Wi-Fi。传完后会自动识别并进入校对。"
        )
        self.lan_start_button.setEnabled(False)
        self.lan_stop_button.setEnabled(True)
        self.capture_status_label.setText("正在等待手机传入截图…")
        self.statusBar().showMessage("无线接收已打开。若传不过来，请允许 Python 通过防火墙。")

    def _stop_lan_receive(self) -> None:
        if self._lan_server is not None:
            self._lan_server.stop()
            self._lan_server = None
        self.lan_start_button.setEnabled(True)
        self.lan_stop_button.setEnabled(False)
        self.lan_code_label.setText("")
        self.statusBar().showMessage("已停止无线接收")

    def _lan_progress(self, payload: object) -> None:
        _task_id, _path, sequence = payload
        self.capture_status_label.setText(f"已收到第 {int(sequence) + 1} 张，继续传…")

    def _lan_complete(self, payload: object) -> None:
        _task_id, paths = payload
        self._stop_lan_receive()
        self._capture_generation += 1
        self._processed_generation = -1
        self._capture_frame_paths = [Path(path) for path in paths]
        if not self._capture_frame_paths:
            QMessageBox.warning(self, "没有收到截图", "手机端请先采完，再点「传到电脑」。")
            return
        self.capture_status_label.setText(f"已收到 {len(self._capture_frame_paths)} 张，正在自动识别…")
        self._process_captured_frames()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_lan_receive()
        event.accept()

    def _start_import(self) -> None:
        self._new_paper("导入试卷")
        self._goto(1, "正在收题")
        self._import_files()

    def _new_paper(self, title: str) -> None:
        self.paper_id = new_paper_id("paper")
        self.paper_title = title
        self.workflow = DesktopWorkflow(self.workflow.engine)
        self.group_ids = []
        self.review_index = 0
        self._refresh_table()

    def _engine_changed(self) -> None:
        self._switch_engine(str(self.engine_combo.currentData()))

    def _switch_engine(self, name: str) -> None:
        try:
            self.workflow.engine = create_ocr_engine(name)
            self.engine_name = name
            self.statusBar().showMessage(f"识别方式：{_ENGINE_LABELS.get(name, name)}")
        except PaddleOcrUnavailable as exc:
            self.workflow.engine = MockOcrEngine()
            self.engine_name = "mock"
            self.engine_combo.blockSignals(True)
            self.engine_combo.setCurrentIndex(0)
            self.engine_combo.blockSignals(False)
            QMessageBox.warning(self, "精确识别还没装好", f"{exc}\n已改回试用识别。")

    def _refresh_recent(self) -> None:
        self.recent_list.clear()
        repository = SQLiteRepository(self.database)
        repository.create_schema()
        for paper in repository.list_papers()[:20]:
            item = QListWidgetItem(f"{paper.title}  ·  {paper.id}  ·  {paper.total_questions} 题")
            item.setData(Qt.ItemDataRole.UserRole, paper.id)
            self.recent_list.addItem(item)

    def _open_selected_paper(self, force: bool = False) -> None:
        item = self.recent_list.currentItem()
        if item is None:
            if force:
                QMessageBox.information(self, "还没有试卷", "先导入截图或采集一套卷。")
            return
        self.paper_id = str(item.data(Qt.ItemDataRole.UserRole))
        self.paper_title = item.text().split("  ·  ", 1)[0]
        self._goto(3, "查看结果")
        self._build_current_paper()

    def _capture_status_changed(self, snapshot: CaptureSnapshot) -> None:
        QTimer.singleShot(0, lambda snap=snapshot: self._render_capture_status(snap))

    def _render_capture_status(self, snapshot: CaptureSnapshot) -> None:
        text = f"已拍 {snapshot.frames_captured} 张"
        if snapshot.message:
            text += f" · {snapshot.message}"
        if snapshot.status is CaptureStatus.NO_DEVICE:
            text = "没找到手机。请打开 USB 调试，或改用手机里的采集伴侣。"
        elif snapshot.status is CaptureStatus.ERROR:
            text = f"采集出了问题：{snapshot.error or snapshot.message}"
        elif snapshot.status is CaptureStatus.RUNNING:
            text = f"正在自动采集，已拍 {snapshot.frames_captured} 张。请留在粉笔解析页。"
        elif snapshot.status in {CaptureStatus.COMPLETED, CaptureStatus.STOPPED}:
            text = f"采集结束，共 {snapshot.frames_captured} 张，正在自动识别…"
        self.capture_status_label.setText(text)
        self.statusBar().showMessage(text)
        active = snapshot.status in {CaptureStatus.CONNECTING, CaptureStatus.RUNNING, CaptureStatus.PAUSED, CaptureStatus.STOPPING}
        self.capture_start_button.setEnabled(not active)
        self.capture_pause_button.setEnabled(snapshot.status is CaptureStatus.RUNNING)
        self.capture_resume_button.setEnabled(snapshot.status is CaptureStatus.PAUSED)
        self.capture_stop_button.setEnabled(active)
        self.capture_process_button.setEnabled(bool(self._ready_frame_paths()) and not active)
        if snapshot.status in {CaptureStatus.COMPLETED, CaptureStatus.STOPPED} and self._ready_frame_paths():
            QTimer.singleShot(120, self._process_captured_frames)

    def _capture_frame_received(self, frame: CaptureFrame) -> None:
        QTimer.singleShot(0, lambda item=frame: self._append_frame(item))

    def _append_frame(self, frame: CaptureFrame) -> None:
        if frame.path:
            self._capture_frame_paths.append(frame.path)

    def _start_capture(self) -> None:
        self._capture_frame_paths.clear()
        self._capture_generation += 1
        self._new_paper("自动采集试卷")
        self.capture_controller.start(wait=False)
        self._render_capture_status(self.capture_controller.snapshot)

    def _pause_capture(self) -> None:
        self._render_capture_status(self.capture_controller.pause())

    def _resume_capture(self) -> None:
        self._render_capture_status(self.capture_controller.resume())

    def _stop_capture(self) -> None:
        self._render_capture_status(self.capture_controller.stop(wait=False))

    def _ready_frame_paths(self) -> list[Path]:
        paths: list[Path] = []
        seen: set[Path] = set()
        for path in [*self._capture_frame_paths, *(frame.path for frame in self.capture_controller.frames if frame.path)]:
            resolved = Path(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(resolved)
        return paths

    def _confirm_process_frames(self) -> None:
        self._process_captured_frames()

    def _process_captured_frames(self) -> None:
        paths = self._ready_frame_paths()
        if not paths or self._processed_generation == self._capture_generation:
            return
        self._processed_generation = self._capture_generation
        engine = self.workflow.engine
        paper_id = self.paper_id
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.capture_status_label.setText("正在用 OCR 识别并归类题目…")

        def run() -> None:
            try:
                result = process_capture_frames(
                    paths,
                    engine=engine,
                    workspace=Path.cwd(),
                    paper_id=paper_id,
                    paper_title=self.paper_title,
                )
            except Exception as exc:
                result = exc
            self._worker_bridge.finished.emit(result)

        threading.Thread(target=run, name="fenbi-processing", daemon=True).start()

    def _pipeline_finished(self, result: object) -> None:
        self.progress.setVisible(False)
        if isinstance(result, Exception):
            self.statusBar().showMessage("整理失败")
            QMessageBox.critical(self, "整理失败", str(result))
            return
        self._adopt_processing_result(result)

    def _adopt_processing_result(self, result: object) -> None:
        self.workflow = result.workflow
        engine = self.workflow.engine
        self.workflow.engine = getattr(engine, "inner", engine)
        self.group_ids = list(result.groups)
        self.review_index = 0
        self._refresh_table()
        self._refresh_recent()
        self.results_label.setText(
            f"题目 {result.questions} 道，待核对 {result.review_count} 道。\n"
            f"错题卷草稿：{result.paper_bundle}"
        )
        if not self.group_ids:
            QMessageBox.warning(self, "没有识别出题目", "请确认截图是已完成、带解析的试卷。")
            return
        self._load_review()
        self._goto(2, "正在校对")
        self.statusBar().showMessage(
            f"已自动识别 {result.questions} 题，其中 {result.review_count} 题还要核对"
        )

    def _build_current_paper(self) -> None:
        try:
            result = rebuild_paper_outputs(self.database, self.paper_id, export_root=self.export_root)
        except Exception as exc:
            QMessageBox.critical(self, "还不能导出", f"请先保存至少一题：{exc}")
            return
        self.results_label.setText(
            f"共 {result.questions} 题，待核对 {result.review_count} 题。\n组卷：{result.paper_bundle}"
        )
        self._goto(3, "导出结果")
        QMessageBox.information(self, "已生成", "错题卷和解析册已写好，可点「打开导出文件夹」。")

    def _export_package(self) -> None:
        try:
            repository = SQLiteRepository(self.database)
            paper = repository.get_paper(self.paper_id)
            questions = repository.list_questions(self.paper_id)
            if paper is None or not questions:
                raise ValueError("这套卷还是空的")
            path = export_mistake_package(
                paper,
                questions,
                self.export_root / f"{self.paper_id}-mistakes.zip",
                media_roots=[Path.cwd() / "data", self.export_root],
            )
        except Exception as exc:
            QMessageBox.critical(self, "导出错题包失败", str(exc))
            return
        QMessageBox.information(self, "错题包已保存", str(path))

    def _export_review(self) -> None:
        try:
            questions = SQLiteRepository(self.database).list_questions(self.paper_id)
            if not questions:
                raise ValueError("这套卷还是空的")
            plan = build_review_plan(questions)
            json_path, md_path = write_review_plan(
                plan,
                self.export_root / "review-plan.json",
                self.export_root / "review-plan.md",
            )
            mind = export_knowledge_mindmap(questions, self.export_root / "knowledge-mindmap.md")
        except Exception as exc:
            QMessageBox.critical(self, "复习计划失败", str(exc))
            return
        QMessageBox.information(self, "复习计划已生成", f"{md_path}\n{mind}")

    def _run_ai_analysis(self) -> None:
        if QMessageBox.question(
            self,
            "调用本机模型？",
            "只会连接本机 Ollama（127.0.0.1:11434）。题目会发给这个本地模型。",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.statusBar().showMessage("正在调用本机模型；粉笔答案保持只读。")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        def run() -> None:
            try:
                result = run_ai_analysis(
                    self.database,
                    self.paper_id,
                    output_root=self.export_root,
                    endpoint="http://127.0.0.1:11434/api/generate",
                    model="local",
                )
            except Exception as exc:
                result = exc
            self._worker_bridge.ai_finished.emit(result)

        threading.Thread(target=run, name="fenbi-ai-analysis", daemon=True).start()

    def _ai_finished(self, result: object) -> None:
        self.progress.setVisible(False)
        if isinstance(result, Exception):
            QMessageBox.critical(self, "本机模型没有响应", str(result))
            return
        QMessageBox.information(self, "分析完成", f"看过 {result.questions_analyzed} 题。\n{result.markdown_path}")

    def _open_export_folder(self) -> None:
        folder = self.export_root / self.paper_id
        folder.mkdir(parents=True, exist_ok=True)
        QMessageBox.information(self, "导出位置", str(folder))

    def _import_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择截图",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)",
        )
        if not files:
            return
        destination = Path.cwd() / "data" / "imports" / self.paper_id
        self.workflow.import_paths(files, destination)
        self._refresh_table()
        self.statusBar().showMessage(f"已导入 {len(self.workflow.images)} 张，正在自动识别…")
        self._ingest_workflow_async()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.workflow.images))
        for row, image in enumerate(self.workflow.images):
            values = [str(image.order + 1), image.path.name, image.group_id, _KIND_LABELS.get(image.page_kind, image.page_kind)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, str(image.path))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _preview_selected(self) -> None:
        rows = sorted({item.row() for item in self.table.selectedItems()})
        if not rows or rows[0] >= len(self.workflow.images):
            return
        self._show_preview(self.workflow.images[rows[0]].path, self.preview)

    def _show_preview(self, path: Path, label: QLabel) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            label.setText(f"无法预览：{path.name}")
            return
        label.setPixmap(
            pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def _assign_selected(self) -> None:
        rows = sorted({item.row() for item in self.table.selectedItems()})
        if not rows:
            QMessageBox.information(self, "还没选图", "先点表格里的截图。")
            return
        group_id = self.group_edit.text().strip()
        if not group_id:
            QMessageBox.warning(self, "缺少题号", "请输入题号，例如 q001。")
            return
        self.workflow.assign(rows, group_id, _KIND_VALUES.get(self.kind_combo.currentText(), "unassigned"))
        self._refresh_table()

    def _auto_group_and_review(self) -> None:
        self._ingest_workflow_async()

    def _ingest_workflow_async(self) -> None:
        if not self.workflow.images:
            QMessageBox.information(self, "还没有截图", "先导入或采集。")
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        workflow = self.workflow
        paper_id = self.paper_id
        paper_title = self.paper_title

        def run() -> None:
            try:
                result = classify_and_persist(
                    workflow,
                    database=self.database,
                    export_root=self.export_root,
                    paper_id=paper_id,
                    paper_title=paper_title,
                )
            except Exception as exc:
                result = exc
            self._worker_bridge.finished.emit(result)

        threading.Thread(target=run, name="fenbi-ocr-classify", daemon=True).start()

    def _load_review(self) -> None:
        if not self.group_ids:
            return
        self.review_index = max(0, min(self.review_index, len(self.group_ids) - 1))
        group_id = self.group_ids[self.review_index]
        self.group_edit.setText(group_id)
        draft = self.workflow.drafts.get(group_id) or self.workflow.recognize_group(group_id)
        self.stem_edit.setPlainText(draft.stem_md)
        self.options_edit.setPlainText("\n".join(f"{key}. {value}" for key, value in draft.options.items()))
        self.user_chips.set_answers(draft.user_answer)
        self.official_chips.set_answers(draft.official_answer)
        self.explanation_edit.setPlainText(draft.official_explanation_md)
        missing = "、".join(draft.missing_required_fields)
        self.status_label.setText("这题可以保存" if not missing else f"还缺：{missing}")
        self.review_progress.setText(f"第 {self.review_index + 1} / {len(self.group_ids)} 题  ·  {group_id}")
        frames = [image for image in self.workflow.images if image.group_id == group_id]
        if frames:
            self._show_preview(frames[0].path, self.review_preview)

    def _apply_review_fields(self) -> None:
        group_id = self.group_ids[self.review_index]
        draft = self.workflow.drafts.get(group_id)
        if draft is None:
            return
        draft.stem_md = self.stem_edit.toPlainText().strip()
        draft.user_answer = self.user_chips.answers()
        if draft.user_answer is None:
            draft.evidence.pop("user_answer", None)
        draft.official_answer = self.official_chips.answers()
        draft.official_explanation_md = self.explanation_edit.toPlainText().strip()
        draft.options = {}
        for line in self.options_edit.toPlainText().splitlines():
            if "." in line:
                label, content = line.split(".", 1)
                draft.options[label.strip().upper()] = content.strip()
        group_images = [image for image in self.workflow.images if image.group_id == group_id]
        for field_name, value in (
            ("stem_md", draft.stem_md),
            ("user_answer", draft.user_answer is not None),
            ("official_answer", draft.official_answer),
            ("official_explanation_md", draft.official_explanation_md),
        ):
            if value and field_name not in draft.evidence:
                draft.evidence[field_name] = [FieldEvidence(str(image.path), (), ()) for image in group_images]
        draft.reviewed = not draft.missing_required_fields
        persist_group(
            self.workflow,
            group_id,
            database=self.database,
            export_root=self.export_root,
            paper_id=self.paper_id,
            paper_title=self.paper_title,
        )

    def _step_review(self, offset: int) -> None:
        if not self.group_ids:
            return
        self._apply_review_fields()
        self.review_index += offset
        self._load_review()

    def _finish_review(self) -> None:
        if self.group_ids:
            self._apply_review_fields()
        self._refresh_recent()
        self._goto(3, "导出结果")
        self._build_current_paper()


def run_gui(engine_name: str = "mock", capture_service=None) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(engine_name, capture_service=capture_service)
    window.show()
    return app.exec()
