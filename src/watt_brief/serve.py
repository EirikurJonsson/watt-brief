"""Run the service: python -m watt_brief.serve

Binds to localhost. Expose it only through the Cloudflare Tunnel, never directly.
"""

import uvicorn

from watt_brief.api import create_app
from watt_brief.config import get_settings
from watt_brief.logging import configure_logging


def main() -> None:
    configure_logging()
    app = create_app(get_settings())
    # access_log off: uvicorn's access log prints request lines, our own log is structured.
    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)


if __name__ == "__main__":
    main()
