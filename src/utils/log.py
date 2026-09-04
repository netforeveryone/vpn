from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_stdout = sys.stdout
_stderr = sys.stderr
_log_file = None


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> None:
        for stream in self._streams:
            stream.write(data)
            stream.flush()

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()

    def isatty(self) -> bool:
        return self._streams[0].isatty()


def setup_run_log(results_dir: Path) -> Path:
    global _log_file

    results_dir.mkdir(parents=True, exist_ok=True)
    log_path = results_dir / "run.log"
    _log_file = log_path.open("a", encoding="utf-8")
    _log_file.write(
        f"\n{'=' * 60}\n"
        f"Run started {datetime.now(timezone.utc).isoformat()}\n"
        f"{'=' * 60}\n"
    )
    _log_file.flush()

    sys.stdout = _Tee(_stdout, _log_file)
    sys.stderr = _Tee(_stderr, _log_file)
    return log_path


def teardown_run_log() -> None:
    global _log_file

    sys.stdout = _stdout
    sys.stderr = _stderr

    if _log_file is not None:
        _log_file.write(f"Run ended {datetime.now(timezone.utc).isoformat()}\n")
        _log_file.close()
        _log_file = None
