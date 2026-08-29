#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

IMPORT_ANCHOR = "from typing import Any, Iterable\n"
IMPORT_LINE = "from week_web import WeekWeb, inject_main_entry\n"
INIT_ANCHOR = "        self.store = AuthStore(config)\n"
INIT_LINE = "        self.week = WeekWeb(\"/var/lib/dvizh/telegram.db\")\n"
PROXY_ANCHOR = "                    payload = response.read()\n"
PROXY_LINE = "                    payload = inject_main_entry(payload, response.getheader(\"Content-Type\", \"\"), self.path)\n"
DISPATCH_ANCHOR = "                if path == \"/auth/account\" and self.command in {\"GET\", \"HEAD\"}:\n"
DISPATCH_BLOCK = """                if path == \"/week\" or path.startswith(\"/week/\"):\n                    if gateway.week.handle(self, session, path):\n                        return\n\n"""


def insert_once(text: str, anchor: str, addition: str, label: str, *, after: bool = True) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition if after else addition + anchor, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="/opt/dvizh-auth/auth_gateway.py")
    args = parser.parse_args()
    path = Path(args.path)
    text = path.read_text(encoding="utf-8")
    text = insert_once(text, IMPORT_ANCHOR, IMPORT_LINE, "import")
    text = insert_once(text, INIT_ANCHOR, INIT_LINE, "gateway init")
    text = insert_once(text, PROXY_ANCHOR, PROXY_LINE, "proxy payload")
    text = insert_once(text, DISPATCH_ANCHOR, DISPATCH_BLOCK, "dispatch", after=False)
    path.write_text(text, encoding="utf-8")
    print("auth gateway patched for /week")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
