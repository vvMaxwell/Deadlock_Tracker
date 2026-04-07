from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

from deadlock_tracker.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "deadlock_tracker.web.app:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
