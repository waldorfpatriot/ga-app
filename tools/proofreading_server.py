#!/usr/bin/env python3
"""Local GA proofreading workspace with durable, exportable editorial notes.

Run: python3 tools/proofreading_server.py --port 4173
Notes are private local editorial data, separate from the reader's user notes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
WORK_ID = re.compile(r"ga-[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def read_json(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Workspace:
    def __init__(self, root=ROOT, database=None):
        self.root = Path(root)
        self.report_root = self.root / "server/priv/proofreading"
        self.catalog_path = self.report_root / "catalog.json"
        self.database = Path(database or self.root / "server/var/proofreading.sqlite3")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, work_id TEXT NOT NULL, passage_id TEXT,
                    quote TEXT NOT NULL, start_offset INTEGER, end_offset INTEGER,
                    checksum TEXT, body TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS notes_work ON notes(work_id);
                CREATE TABLE IF NOT EXISTS reviews (
                    work_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            """)
        self.database.chmod(0o600)

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def catalog(self):
        return read_json(self.catalog_path)

    def work(self, work_id):
        if not WORK_ID.fullmatch(work_id):
            raise ValueError("Ungültige GA-Kennung.")
        report_path = self.report_root / "works" / (work_id + ".json")
        if not report_path.exists():
            raise KeyError(work_id)
        report = read_json(report_path)
        passages = []
        table_of_contents = []
        if report["work"]["available"]:
            content_root = self.root / "server/priv/content"
            candidates = [content_root / (work_id + suffix) for suffix in (".json.gz", ".json")]
            payload = read_json(next(path for path in candidates if path.exists()))
            passages = payload["passages"]
            table_of_contents = payload.get("table_of_contents", [])
        return {**report, "passages": passages, "table_of_contents": table_of_contents}

    def notes(self, work_id=None):
        with self.connect() as db:
            query = "SELECT * FROM notes" + (" WHERE work_id = ?" if work_id else "") + " ORDER BY created_at, id"
            notes = [dict(row) for row in db.execute(query, (work_id,) if work_id else ())]
            reviews = [dict(row) for row in db.execute("SELECT * FROM reviews ORDER BY work_id")]
        return {"notes": notes, "reviews": reviews}

    def save_note(self, body, note_id=None):
        existing = None
        if note_id:
            with self.connect() as db:
                row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if not row:
                raise KeyError(note_id)
            existing = dict(row)
        record = {**existing, "body": body.get("body", existing["body"]), "status": body.get("status", existing["status"])} if existing else dict(body)
        work_id = record.get("work_id", "")
        detail = self.work(work_id)
        passage_id = record.get("passage_id") or None
        quote = record.get("quote") or ""
        content = record.get("body", "")
        status = record.get("status", "open")
        if not isinstance(content, str) or not content.strip() or len(content) > 20000:
            raise ValueError("Die Notiz muss 1 bis 20000 Zeichen enthalten.")
        if not isinstance(quote, str) or len(quote) > 20000:
            raise ValueError("Ungültiges Zitat.")
        if status not in {"open", "resolved"}:
            raise ValueError("Ungültiger Notizstatus.")
        passage = None
        if passage_id:
            passage = next((p for p in detail["passages"] if p["id"] == passage_id), None)
            if not passage:
                raise ValueError("Dieser Abschnitt gehört nicht zum Band.")
            if not existing and record.get("checksum") and record["checksum"] != passage.get("checksum"):
                raise ValueError("Der Abschnitt wurde geändert. Bitte neu laden und das Zitat erneut auswählen.")
        if quote and (not passage or quote not in passage["text"]):
            # Existing anchors remain exportable after a later corpus update.
            if not existing or quote != existing["quote"]:
                raise ValueError("Das Zitat gehört nicht zum aktuellen Abschnitt.")
        start, end = record.get("start_offset"), record.get("end_offset")
        if start is not None or end is not None:
            if type(start) is not int or type(end) is not int or start < 0 or end < start or not passage:
                raise ValueError("Ungültige Textposition.")
            encoded = passage["text"].encode("utf-16-le")
            if end * 2 > len(encoded):
                raise ValueError("Textposition liegt außerhalb des Abschnitts.")
            selected = encoded[start * 2:end * 2].decode("utf-16-le", errors="replace")
            if selected != quote and not existing:
                raise ValueError("Zitat und Textposition stimmen nicht überein.")
        now = timestamp()
        values = {
            "id": note_id or str(uuid.uuid4()), "work_id": work_id,
            "passage_id": passage_id, "quote": quote, "start_offset": start,
            "end_offset": end, "checksum": (existing or {}).get("checksum") or (passage or {}).get("checksum"),
            "body": content.strip(), "status": status,
            "created_at": (existing or {}).get("created_at", now), "updated_at": now,
        }
        with self.connect() as db:
            db.execute("""INSERT INTO notes VALUES (:id,:work_id,:passage_id,:quote,:start_offset,
                :end_offset,:checksum,:body,:status,:created_at,:updated_at)
                ON CONFLICT(id) DO UPDATE SET body=excluded.body,status=excluded.status,
                updated_at=excluded.updated_at""", values)
        return values

    def delete_note(self, note_id):
        with self.connect() as db:
            cursor = db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            if not cursor.rowcount:
                raise KeyError(note_id)

    def review(self, work_id, status):
        work = self.work(work_id)["work"]
        if status not in {"unreviewed", "in_progress", "reviewed"}:
            raise ValueError("Ungültiger Prüfstatus.")
        if status == "reviewed" and not work["available"]:
            raise ValueError("Ein Band ohne Text kann nicht als gelesen markiert werden.")
        record = {"work_id": work_id, "status": status, "updated_at": timestamp()}
        with self.connect() as db:
            db.execute("""INSERT INTO reviews VALUES (:work_id,:status,:updated_at)
                ON CONFLICT(work_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at""", record)
        return record

    def export(self, format="json"):
        payload = {"schema_version": 1, "exported_at": timestamp(), "offset_encoding": "utf-16", **self.notes()}
        if format == "json":
            return json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "application/json; charset=utf-8", "ga-korrekturen.json"
        if format != "markdown":
            raise ValueError("Unbekanntes Exportformat.")
        works = {w["id"]: w for w in self.catalog()["works"]}
        lines = ["# GA-Korrekturen", "", f"Export: {payload['exported_at']}", ""]
        selected = sorted({n["work_id"] for n in payload["notes"]} | {r["work_id"] for r in payload["reviews"]})
        for work_id in selected:
            work = works[work_id]
            lines.extend([f"## {work['ga_number']} · {work['title']}", ""])
            review = next((r for r in payload["reviews"] if r["work_id"] == work_id), {})
            lines.extend(["Prüfstatus: " + review.get("status", "unreviewed"), ""])
            for note in payload["notes"]:
                if note["work_id"] != work_id:
                    continue
                lines.extend([f"### Notiz {note['id']} ({note['status']})", "", "Abschnitt: " + (note["passage_id"] or "Bandnotiz"), ""])
                if note["quote"]:
                    lines.extend(["> " + line for line in note["quote"].splitlines()] + [""])
                lines.extend([note["body"], ""])
        return "\n".join(lines), "text/markdown; charset=utf-8", "ga-korrekturen.md"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server,
                         directory=str(server.workspace.root / "server/priv/static"))

    def send_data(self, status, data, content_type="application/json; charset=utf-8", filename=None):
        encoded = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, (bytes, str)) else data.encode() if isinstance(data, str) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    def dispatch(self):
        url = urlsplit(self.path)
        path, query = url.path, parse_qs(url.query)
        workspace = self.server.workspace
        if self.command in {"GET", "HEAD"}:
            if path == "/api/proofreading/catalog":
                return self.send_data(200, workspace.catalog())
            if path.startswith("/api/proofreading/works/"):
                return self.send_data(200, workspace.work(path.rsplit("/", 1)[-1]))
            if path == "/api/proofreading/notes":
                return self.send_data(200, workspace.notes(query.get("work_id", [None])[0]))
            if path == "/api/proofreading/export":
                text, content_type, filename = workspace.export(query.get("format", ["json"])[0])
                return self.send_data(200, text, content_type, filename)
            raise KeyError(path)
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            return self.send_data(403, {"error": "Notizen müssen aus dieser Arbeitsansicht gespeichert werden."})
        length = int(self.headers.get("Content-Length", 0))
        if length < 0 or length > 100000:
            return self.send_data(413, {"error": "Anfrage zu groß."})
        if self.command != "DELETE" and not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send_data(415, {"error": "JSON erwartet."})
        body = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(body, dict):
            raise ValueError("JSON-Objekt erwartet.")
        if self.command == "POST" and path == "/api/proofreading/notes":
            return self.send_data(201, {"note": workspace.save_note(body)})
        if path.startswith("/api/proofreading/notes/"):
            note_id = path.rsplit("/", 1)[-1]
            if self.command == "PUT":
                return self.send_data(200, {"note": workspace.save_note(body, note_id)})
            if self.command == "DELETE":
                workspace.delete_note(note_id)
                return self.send_data(200, {"deleted": note_id})
        if self.command == "PUT" and path.startswith("/api/proofreading/reviews/"):
            return self.send_data(200, {"review": workspace.review(path.rsplit("/", 1)[-1], body.get("status"))})
        raise KeyError(path)

    def api(self):
        try:
            self.dispatch()
        except KeyError:
            self.send_data(404, {"error": "Eintrag nicht gefunden."})
        except (ValueError, TypeError, UnicodeError) as error:
            self.send_data(400, {"error": str(error)})
        except Exception:
            self.send_data(500, {"error": "Die Arbeitsdaten konnten nicht gelesen oder gespeichert werden."})

    def do_GET(self):
        if urlsplit(self.path).path.startswith("/api/"):
            return self.api()
        if urlsplit(self.path).path == "/":
            self.send_response(302)
            self.send_header("Location", "/proofreading/")
            self.end_headers()
            return
        if not urlsplit(self.path).path.startswith("/proofreading/"):
            return self.send_data(404, {"error": "Nicht gefunden."})
        super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path.startswith("/api/"):
            return self.api()
        super().do_HEAD()

    def do_POST(self):
        self.api()

    do_PUT = do_POST
    do_DELETE = do_POST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    workspace = Workspace(database=args.database)
    if not workspace.catalog_path.exists():
        parser.error("Run tools/proofread_library.py first to generate the per-volume reports.")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.workspace = workspace
    print(f"GA proofreading: http://127.0.0.1:{args.port}/proofreading/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
