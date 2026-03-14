from __future__ import annotations

import uvicorn

from .api import create_app


def cli() -> None:
    uvicorn.run(
        create_app(),
        host="0.0.0.0",  # noqa: S104
        port=7860,
    )
