"""picture-analysis 入口：python server.py → http://127.0.0.1:8321"""

from __future__ import annotations

import uvicorn

from app.main import create_app

app = create_app()


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8321, log_level="info")


if __name__ == "__main__":
    main()
