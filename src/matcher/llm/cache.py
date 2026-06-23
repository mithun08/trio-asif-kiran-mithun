from __future__ import annotations

import os
from pathlib import Path


def configure_dspy_cache(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DSP_CACHEDIR"] = str(cache_dir)
