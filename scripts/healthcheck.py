"""Simple healthcheck script for Docker."""

import sys


def main() -> None:
    try:
        import httpx

        r = httpx.get("https://api.telegram.org", timeout=5)
        if r.status_code < 500:
            sys.exit(0)
    except Exception:
        pass
    sys.exit(1)


if __name__ == "__main__":
    main()
