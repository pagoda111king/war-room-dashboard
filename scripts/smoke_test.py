#!/usr/bin/env python3
"""Smoke checks for War Room Dashboard."""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "app" / "server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("war_room_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_db_init() -> None:
    server = load_server_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "项目台.db"
        server.DB = str(db_path)
        server.init_db()
        conn = sqlite3.connect(db_path)
        counts = {}
        for table in ("projects", "tasks", "plans", "cards"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()
    missing = [table for table, count in counts.items() if count <= 0]
    if missing:
        raise AssertionError(f"Seed data missing for: {', '.join(missing)}")
    print(json.dumps({"ok": True, "mode": "db-init", "counts": counts}, ensure_ascii=False))


def check_running_server(url: str) -> None:
    health_url = url.rstrip("/") + "/api/health"
    with urllib.request.urlopen(health_url, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise AssertionError(f"Health check failed: {payload}")
    if payload.get("counts", {}).get("projects", 0) <= 0:
        raise AssertionError(f"No projects returned in health payload: {payload}")
    print(json.dumps({"ok": True, "mode": "http", "health": payload}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-init-only", action="store_true", help="Verify SQLite init and seed without starting HTTP.")
    parser.add_argument("--url", help="Verify a running dashboard server, for example http://127.0.0.1:8766.")
    args = parser.parse_args()

    if args.url:
        check_running_server(args.url)
        return

    check_db_init()


if __name__ == "__main__":
    main()
