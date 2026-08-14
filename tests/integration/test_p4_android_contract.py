from pathlib import Path


ROOT = Path(__file__).parents[2]
ANDROID = ROOT / "apps" / "android-capture" / "app"
SRC = ANDROID / "src" / "main"


def test_android_manifest_declares_capture_service_and_permissions():
    manifest = (SRC / "AndroidManifest.xml").read_text(encoding="utf-8")
    for permission in (
        "FOREGROUND_SERVICE",
        "FOREGROUND_SERVICE_MEDIA_PROJECTION",
        "SYSTEM_ALERT_WINDOW",
        "INTERNET",
    ):
        assert permission in manifest
    assert "CaptureForegroundService" in manifest
    assert 'android:foregroundServiceType="mediaProjection"' in manifest
    assert "POST_NOTIFICATIONS" not in manifest
    assert "ACCESS_NETWORK_STATE" not in manifest
    assert "com.fenbi.android.solar" not in manifest
    assert 'android.intent.category.LAUNCHER' not in manifest.split("<application", 1)[0]


def test_android_capture_contract_has_projection_checkpoint_and_fallback():
    files = {path.name: path.read_text(encoding="utf-8") for path in (SRC / "java").rglob("*.kt")}
    combined = "\n".join(files.values())
    for token in (
        "MediaProjection",
        "VirtualDisplay",
        "ImageReader",
        "CaptureSessionState",
        "lastSequence",
        "lastTransferredSequence",
        "FALLBACK_SEMI_AUTO",
        "SHA-256",
        "SharedPreferencesTaskStore",
    ):
        assert token in combined
    assert "class LanTransferClient" in combined
    assert "class UsbTransferClient" in combined
    assert "class CaptureModeController" in combined
    assert "onAutomaticFailure" in combined
    assert "FenbiAppGuard" in combined
    assert "launchInstalledFenbi" in combined
    assert "BLOCKED_PACKAGES" in combined
    assert "com.fenbi.android.solar" in combined
    assert "本软件不登录粉笔" in combined
    assert "JinzhiStudyApp" in combined
    assert "ReviewPlanner" in combined
    assert "jinzhi-mistake-package" in combined
    assert "StudyFilters" in combined
    assert "WrongPaperHtml" in combined
    assert "今知错题卷" in combined
    assert "丁真自动翻页" in combined
    assert "丁真笔记本" in combined
    assert "android.settings.ACCESSIBILITY_DETAILS_SETTINGS" in combined
    assert "已下载的服务" in combined
    assert "PermissionCoachOverlay" in combined
    assert "点我进入开关页" in combined
    assert "WAIT_FOR_LOGIN" in combined
    assert "OPEN_ANALYSIS" in combined
    assert "FINISH_PAPER" in combined
    assert "parsePairingCode" in combined
    assert "isPrivateLanHost" in combined
    assert "/complete" in combined
    assert "FENBI1|" in combined


def test_android_modes_are_explicit_and_no_secret_storage_is_declared():
    contracts = (SRC / "java" / "com" / "local" / "fenbistudy" / "capture" / "CaptureContracts.kt").read_text(encoding="utf-8")
    assert all(mode in contracts for mode in ("MANUAL", "SEMI_AUTO", "AUTO"))
    assert "password" not in contracts.lower()
    assert "token" not in contracts.lower()
