"""Launch Chainlit while mirroring all console output to logs/chainlit/.

Usage (same arguments as the chainlit CLI):
    python -m src.run_logged run src/chainlit_app/app.py --port 3000

Writes logs/chainlit/<timestamp>_console.log containing everything printed to
stdout/stderr (print(), uvicorn output, tracebacks) plus native-crash dumps via
faulthandler.  The normal logging-module file (<timestamp>_chainlit.log) is
still produced by the app itself.  The process exit code is preserved so the
.bat watchdog's restart logic keeps working.
"""
from __future__ import annotations

import faulthandler
import re
import runpy
import sys
from datetime import datetime
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class _Tee:
    def __init__(self, stream, log):
        self._stream = stream
        self._log = log

    def write(self, data):
        n = self._stream.write(data) if self._stream else len(data)
        try:
            self._log.write(_ANSI.sub("", data))
        except Exception:
            pass
        return n

    def flush(self):
        for s in (self._stream, self._log):
            try:
                if s:
                    s.flush()
            except Exception:
                pass

    def __getattr__(self, name):  # isatty, encoding, fileno, ...
        return getattr(self._stream, name)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    log_dir = root / "logs" / "chainlit"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log = open(log_dir / f"{stamp}_console.log", "a", encoding="utf-8", errors="replace", buffering=1)
    faulthandler.enable(file=log, all_threads=True)
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    sys.argv = ["chainlit"] + sys.argv[1:]
    runpy.run_module("chainlit", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
