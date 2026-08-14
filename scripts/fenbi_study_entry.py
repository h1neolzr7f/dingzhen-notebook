import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from apps.desktop.main import main


if __name__ == "__main__":
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    arguments = sys.argv[1:] or ["--ocr-engine", "paddle"]
    try:
        raise SystemExit(main(arguments))
    except SystemExit:
        raise
    except BaseException:
        # A windowed executable has no stderr console.  Preserve an actionable
        # traceback instead of failing silently if a third-party runtime breaks.
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        log_dir = local_app_data / "FenbiStudy" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "crash.log"
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(f"\n[{datetime.now(timezone.utc).isoformat()}]\n")
            traceback.print_exc(file=stream)
        raise
