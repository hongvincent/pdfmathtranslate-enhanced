from __future__ import annotations

import asyncio
import os

from .runner import worker_loop


def cli() -> None:
    worker_name = os.environ.get("PDF2ZH_ENHANCED_WORKER_NAME")
    asyncio.run(worker_loop(worker_name))
