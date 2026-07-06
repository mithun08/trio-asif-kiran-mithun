from __future__ import annotations

import subprocess
import sys


def test_importing_cli_raises_fd_soft_limit() -> None:
    script = (
        "import resource\n"
        "soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)\n"
        "resource.setrlimit(resource.RLIMIT_NOFILE, (min(256, hard), hard))\n"
        "import matcher.cli\n"
        "print(resource.getrlimit(resource.RLIMIT_NOFILE)[0])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) >= 8192
