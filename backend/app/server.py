"""Production entry point: trusted LAN decisions use transport peers, never XFF."""

import uvicorn
from .config import Settings


def main():
    settings = Settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8085,
        workers=1,
        proxy_headers=settings.backup_auth_mode == "password",
    )


if __name__ == "__main__":
    main()
