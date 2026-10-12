#!/usr/bin/env python3
"""Generate isolated author deployments and validated static reader snapshots.

This command only writes local, reproducible files. The generated host installer
defaults to a read-only preflight; secrets are created only on the Linux host.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

from import_author_library import original_languages, validated_timestamp


ROOT = Path(__file__).resolve().parents[1]
SAFE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PRIVATE_KEYS = {"source_text", "access_token", "recovery_code", "message_ciphertext"}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def reader_safe(value):
    if isinstance(value, dict):
        if PRIVATE_KEYS.intersection(value):
            raise ValueError("Private data cannot appear in a public reader snapshot")
        for item in value.values():
            reader_safe(item)
    elif isinstance(value, list):
        for item in value:
            reader_safe(item)


def read_json(path):
    if path.is_symlink():
        raise ValueError(f"Symlink not allowed in reader inputs: {path}")
    value = json.loads(path.read_text())
    reader_safe(value)
    return value


def load_authors(path):
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("authors"), list) or not manifest["authors"]:
        raise ValueError("Expected schema_version 1 and a nonempty authors list")
    seen = {key: set() for key in ["slug", "service_name", "database", "port", "reader_base_url", "access_base_url", "bundle_id"]}
    authors = []
    for original in manifest["authors"]:
        author = copy.deepcopy(original)
        slug = author.get("slug", "")
        if not SAFE_ID.fullmatch(slug) or len(slug) > 28:
            raise ValueError("Invalid author slug")
        if author.get("service_name") != "author-" + slug:
            raise ValueError(f"Invalid isolated service for {slug}")
        if author.get("database") != "author_" + slug.replace("-", "_"):
            raise ValueError(f"Invalid isolated database for {slug}")
        if not isinstance(author.get("port"), int) or not 1024 <= author["port"] <= 65535 or author["port"] in {4000, 4131}:
            raise ValueError(f"Invalid isolated port for {slug}")
        for field, suffix in [("access_base_url", slug), ("reader_base_url", slug + "-reader")]:
            url = urlsplit(author.get(field, ""))
            if (url.scheme != "https" or not url.hostname or not re.fullmatch(r"[A-Za-z0-9.-]+", url.hostname) or url.username or url.password
                    or url.port or url.query or url.fragment or url.path != "/" + suffix):
                raise ValueError(f"Invalid {field} for {slug}")
        if urlsplit(author["access_base_url"]).hostname != urlsplit(author["reader_base_url"]).hostname:
            raise ValueError("Reader and access must use the same hosting domain")
        if not isinstance(author.get("author_name"), str) or not author["author_name"].strip():
            raise ValueError("Missing author name")
        if author.get("language") or "original_languages" in author:
            original_languages(author)
        if not re.fullmatch(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)+", author.get("bundle_id", "")):
            raise ValueError("Invalid app bundle identifier")
        for key in seen:
            if author[key] in seen[key]:
                raise ValueError(f"Duplicate author isolation value: {key}")
            seen[key].add(author[key])
        author["os_user"] = "ga-" + slug
        author["reader_root"] = "/var/lib/" + author["service_name"] + "-reader"
        author["web_root"] = "/var/lib/" + author["service_name"] + "-web"
        authors.append(author)
    return authors


def export_reader(author, edition):
    """Mirror GA's public API shape, hashing the exact bytes clients download."""
    if any(path.is_symlink() for path in [edition, edition / "library", edition / "library/content"]):
        raise ValueError("Reader input directories must not be symlinks")
    catalog = read_json(edition / "library/catalog.json")
    if not isinstance(catalog.get("works"), list) or not catalog["works"]:
        raise ValueError(f"Empty author catalog: {author['slug']}")
    timestamp = validated_timestamp(catalog.get("generated_at"), "Catalog")
    languages = original_languages(author) if author.get("language") or "original_languages" in author else None
    policy = {"author_scope": author["slug"].replace("-", "_") + "_original_text_only",
              "languages": "original_languages_only", "complete_volumes_only": True,
              "excludes": ["publisher_pages", "modern_editorial_notes", "introductions_by_other_authors", "protected_apparatus"],
              "user_sync": "cloudkit_private_database"}
    catalog.update({"edition": "independent-public-domain", "audience": "reader", "content_policy": policy})
    files = {}
    work_ids = set()
    downloads = 0
    for work in catalog["works"]:
        work_id = work.get("id", "")
        if not isinstance(work_id, str) or not SAFE_ID.fullmatch(work_id) or work_id in work_ids:
            raise ValueError("Invalid or duplicate work identifier")
        work_ids.add(work_id)
        if work.get("author") != author["author_name"]:
            raise ValueError(f"Catalog author mismatch: {work_id}")
        if languages and work.get("language") not in languages:
            raise ValueError(f"Catalog language differs from original-language edition: {work_id}")
        if not isinstance(work.get("title"), str) or not work["title"].strip():
            raise ValueError(f"Catalog work has no title: {work_id}")
        if work.get("state") == "published_seed":
            raise ValueError(f"Excerpt cannot be advertised as a complete work: {work_id}")
        bundles = []
        if work.get("content_path"):
            path = "/api/catalog/" + work_id + "/content"
            if work["content_path"] != path or work.get("content_completeness") != "complete":
                raise ValueError(f"Invalid completeness declaration: {work_id}")
            payload = read_json(edition / "library/content" / (work_id + ".json"))
            if "language" in payload and payload["language"] != work.get("language"):
                raise ValueError(f"Catalog/content language mismatch: {work_id}")
            passages = payload.get("passages")
            if (payload.get("work_id") != work_id or payload.get("content_completeness") != "complete"
                    or payload.get("completeness", "complete") != "complete" or payload.get("state") == "published_seed"
                    or not isinstance(passages, list) or not passages
                    or payload.get("passage_count") != len(passages)):
                raise ValueError(f"Incomplete reader bundle: {work_id}")
            ids = [p.get("id") for p in passages]
            metadata = work.get("passages", [])
            if (any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids)
                    or ids != [p.get("id") for p in metadata]
                    or work.get("catalog_passage_count") != len(ids)):
                raise ValueError(f"Catalog/content passage mismatch: {work_id}")
            for passage, advertised in zip(passages, metadata):
                body = passage.get("text")
                if not isinstance(body, str) or not body.strip():
                    raise ValueError(f"Empty reader passage: {work_id}")
                if any(not isinstance(passage.get(key), str) for key in ["title", "source_label"]):
                    raise ValueError(f"Invalid reader passage metadata: {work_id}")
                checksum = hashlib.sha256(body.encode()).hexdigest()
                if checksum != passage.get("checksum") or checksum != advertised.get("checksum"):
                    raise ValueError(f"Stale text checksum: {work_id}")
                for key in ("title", "source_label", "ga_page"):
                    if passage.get(key) != advertised.get(key):
                        raise ValueError(f"Catalog passage metadata differs: {work_id}")
            payload["content_path"] = path
            body = json_bytes(payload)
            checksum = hashlib.sha256(body).hexdigest()
            work["content_revision"] = checksum
            work["content_updated_at"] = validated_timestamp(work.get("content_updated_at", timestamp), work_id)
            files[path.lstrip("/")] = body
            bundles.append({"id": work_id + "-text", "kind": "json_text_bundle", "status": "available_on_demand",
                            "platform": "ios_ipados_macos", "content_path": path, "content_completeness": "complete",
                            "checksum": checksum, "checksum_algorithm": "sha256", "byte_size": len(body), "passages": ids})
            downloads += 1
        else:
            if work.get("content_completeness") != "unavailable":
                raise ValueError(f"Unavailable work cannot be advertised complete: {work_id}")
            work.pop("content_revision", None)
            work.pop("content_updated_at", None)
        manifest_work = {key: work[key] for key in ["id", "ga_number", "title", "language", "state", "proofing_state",
                                                   "content_completeness", "content_path", "content_revision", "content_updated_at"] if key in work}
        manifest = {"edition": "independent-public-domain", "generated_by": "ga_server", "work": manifest_work,
                    "content_policy": policy, "bundles": bundles, "sanity_checks": work.get("sanity_checks", [])}
        files[f"api/catalog/{work_id}/index.json"] = json_bytes({"work": work})
        files[f"api/catalog/{work_id}/manifest"] = json_bytes(manifest)
    files["catalog.json"] = files["api/catalog/index.json"] = json_bytes(catalog)
    return files, len(catalog["works"]), downloads


def nginx(author):
    slug, port, root = author["slug"], author["port"], author["reader_root"]
    pages = f'''location = /{slug} {{ return 301 /{slug}/; }}
'''
    for route, filename in [("/", "index.html"), ("/index.html", "index.html"), ("/privacy.html", "privacy.html"), ("/support.html", "support.html")]:
        pages += f'''location = /{slug}{route} {{
    root {author['web_root']}/current;
    try_files /{filename} =404;
    default_type text/html;
    add_header X-Content-Type-Options nosniff always;
    add_header Content-Security-Policy "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'" always;
    add_header Cache-Control "public, max-age=3600";
}}
'''
    return f'''# Include once inside the existing {urlsplit(author['access_base_url']).hostname} HTTPS server block.
# The shared Phoenix release exposes only isolated access and health here.
location ^~ /{slug}/api/access/ {{
    proxy_pass http://127.0.0.1:{port}/api/access/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Authorization $http_authorization;
    client_max_body_size 64k;
    proxy_connect_timeout 5s;
    proxy_read_timeout 15s;
    proxy_send_timeout 15s;
    proxy_cache off;
    add_header X-Content-Type-Options nosniff always;
}}
location = /{slug}/api/health {{
    proxy_pass http://127.0.0.1:{port}/api/health;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_cache off;
    add_header Cache-Control "no-store" always;
}}
location ^~ /{slug}/api/ {{ return 404; }}

# Exact public app pages; no broad routing into the Phoenix application.
{pages}

# This tree contains validated public reader data only, never access data.
location ^~ /{slug}-reader/ {{
    root {root}/current;
    rewrite ^/{slug}-reader/(.*)$ /$1 break;
    try_files $uri $uri/index.json =404;
    index index.json;
    default_type application/json;
    add_header X-Content-Type-Options nosniff always;
    add_header Cache-Control "public, max-age=0, must-revalidate" always;
}}
'''


def host_installer(identity):
    # Keep the same reviewed installer in every edition with immutable identity.
    return HOST_INSTALLER.replace("__IDENTITY__", repr(identity))


def generate_files(author, edition):
    service = author["service_name"]
    identity = {key: author[key] for key in ["slug", "author_name", "service_name", "database", "port", "os_user", "reader_root", "web_root"]}
    identity["host"] = urlsplit(author["access_base_url"]).hostname
    identity["pool_size"] = 2
    files, works, downloads = export_reader(author, edition)
    result = {"reader/" + key: value for key, value in files.items()}
    result["reader-inventory.json"] = json_bytes({"schema_version": 1, "slug": author["slug"], "works": works,
        "downloads": downloads, "files": {key: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()} for key, body in sorted(files.items())}})
    web = {}
    if (edition / "web").is_symlink():
        raise ValueError("Public app-page directory must not be symlinked")
    for name in ["index.html", "privacy.html", "support.html"]:
        path = edition / "web" / name
        if path.is_symlink():
            raise ValueError("Public app pages must not be symlinked")
        body = path.read_bytes()
        if not body.strip():
            raise ValueError("Public app page is empty: " + name)
        web[name] = body
        result["web/" + name] = body
    result["web-inventory.json"] = json_bytes({"schema_version": 1, "slug": author["slug"], "files":
        {key: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()} for key, body in sorted(web.items())}})
    templates = ROOT / "server/deploy"
    unit = (templates / "ga-access.service").read_text().replace("GA solidarity access API", author["author_name"] + " solidarity access API")
    unit = unit.replace("ga-access", service).replace("User=" + service, "User=" + author["os_user"]).replace("Group=" + service, "Group=" + author["os_user"]).replace("MemoryMax=512M", "MemoryHigh=192M\nMemoryMax=256M")
    unit = unit.replace("+S 2:2 +A 4", "+S 1:1 +SDcpu 1 +SDio 1 +A 1")
    unit = unit.replace("Environment=RELEASE_DISTRIBUTION=none", "Environment=RELEASE_DISTRIBUTION=none\nEnvironment=RELEASE_MODE=interactive")
    unit = unit.replace("StateDirectory=" + service, "Slice=author-apps.slice\nStateDirectory=" + service)
    result["access.service"] = unit.encode()
    result["author-apps.slice"] = b'''# Managed shared capacity guard for author services only; never GA.
[Unit]
Description=Independent author access services

[Slice]
MemoryHigh=896M
MemoryMax=1024M
MemorySwapMax=128M
'''
    result["nginx.conf"] = nginx(author).encode()
    environment = (templates / "ga-access.environment.example").read_text().replace("ga-access", service)
    environment = environment.replace("PHX_HOST=fototausch.eu", "PHX_HOST=" + identity["host"]).replace("PORT=4131", "PORT=" + str(author["port"])).replace("ga_access", author["database"]).replace("POOL_SIZE=10", "POOL_SIZE=2")
    result["environment.example"] = environment.encode()
    for original, generated in [("ga-access-backup.sh", "backup.sh"), ("ga-access-backup.service", "backup.service"), ("ga-access-backup.timer", "backup.timer")]:
        template = (templates / original).read_text().replace("ga-access", service).replace("ga_access", author["database"]).replace("GA access", author["author_name"] + " access")
        if generated == "backup.timer":
            template = template.replace("03:15:00", f"03:{15 + (author['port'] - 4140) % 40:02}:00")
        result[generated] = template.encode()
    result["initialize-host.py"] = host_installer(identity).encode()
    result["identity.json"] = json_bytes(identity)
    return result


def write_files(destination, files, check=False, dry_run=False):
    if destination.is_symlink() or (destination.exists() and any(p.is_symlink() for p in destination.rglob("*"))):
        raise ValueError("Generated deploy destination must not contain symlinks")
    changed = [name for name, body in files.items() if not (destination / name).is_file() or (destination / name).read_bytes() != body]
    actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file() or p.is_symlink()} if destination.exists() else set()
    extra = actual - files.keys()
    if any(not name.startswith(("reader/", "web/")) for name in extra):
        raise ValueError("Unexpected operational files in generated deploy tree; preserve them before regenerating")
    changed.extend(sorted(extra))
    if check and changed:
        raise ValueError(f"Generated infrastructure is stale: {destination} ({len(changed)} files)")
    if check or dry_run:
        return len(changed)
    # Replace only this managed deploy tree. A staged tree avoids partial output
    # after content validation failure and removes withdrawn public downloads.
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".deploy-", dir=destination.parent))
    try:
        for name, body in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            path.chmod(0o755 if name in {"backup.sh", "initialize-host.py"} else 0o644)
        previous = destination.with_name(".deploy-previous")
        if previous.exists():
            raise ValueError(f"Interrupted generator backup needs review: {previous}")
        if destination.exists():
            destination.rename(previous)
        staging.rename(destination)
        if previous.exists():
            shutil.rmtree(previous)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return len(changed)


HOST_INSTALLER = r'''#!/usr/bin/env python3
"""Read-only host preflight by default; --apply initializes this isolated service.

Run on the Linux host with a Linux-built shared ga_server release. This installs
service/backup files and migrates the new database. It leaves nginx inclusion,
service activation, and backup activation as explicit deployment steps.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import secrets
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

IDENTITY = __IDENTITY__
HERE = Path(__file__).resolve().parent


def run(command, input=None, private=False):
    result = subprocess.run(command, input=input, capture_output=True, text=True)
    if result.returncode:
        # PostgreSQL errors can echo SQL including a new password.
        detail = "private command failed" if private else result.stderr.strip()
        raise RuntimeError(command[0] + ": " + detail)
    return result.stdout.strip()


def postgres(sql, private=False):
    return run(["runuser", "-u", "postgres", "--", "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "postgres"], input=sql, private=private)


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(data)


def preflight(release):
    if platform.system() != "Linux":
        raise RuntimeError("Initialization must run on the Linux production host")
    if os.geteuid() != 0:
        raise RuntimeError("Root is required to inspect isolated host resources")
    for command in ["useradd", "runuser", "psql", "createdb", "pg_dump", "pg_restore", "openssl", "systemctl", "nginx"]:
        if not shutil.which(command):
            raise RuntimeError("Missing host dependency: " + command)
    shared_slice = Path("/etc/systemd/system/author-apps.slice")
    if shared_slice.exists() and (shared_slice.is_symlink() or shared_slice.read_bytes() != (HERE / "author-apps.slice").read_bytes()):
        raise RuntimeError("Existing author capacity guard is not the managed definition")
    if release and (not (release / "bin/ga_server").is_file() or not (release / "releases/start_erl.data").is_file()):
        raise RuntimeError("Release has no ga_server binary or Erlang release metadata")
    inventory = json.loads((HERE / "reader-inventory.json").read_text())
    for tree in ["reader", "web"]:
        data_inventory = json.loads((HERE / (tree + "-inventory.json")).read_text())
        source = HERE / tree
        expected = set(data_inventory["files"])
        actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
        if actual != expected or source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
            raise RuntimeError("Public file inventory mismatch: " + tree)
        for name, info in data_inventory["files"].items():
            data = (source / name).read_bytes()
            if len(data) != info["bytes"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise RuntimeError("Public integrity failure: " + name)
    config = Path("/etc") / IDENTITY["service_name"]
    owned = config / "identity.json"
    if config.is_symlink() or owned.is_symlink():
        raise RuntimeError("Protected configuration must not be symlinked")
    managed = owned.exists() and json.loads(owned.read_text()) == IDENTITY
    if config.exists() and not managed:
        raise RuntimeError("Existing configuration has a different ownership identity")
    try:
        user = pwd.getpwnam(IDENTITY["os_user"])
    except KeyError:
        user = None
    if user and not managed:
        raise RuntimeError("Existing OS user is not managed by this edition")
    database = IDENTITY["database"]
    existing = postgres("SELECT 'role' FROM pg_roles WHERE rolname='" + database + "' UNION ALL SELECT 'database' FROM pg_database WHERE datname='" + database + "';")
    if existing and not managed:
        raise RuntimeError("Existing database/role is not managed by this edition")
    if managed and set(existing.splitlines()) != {"role", "database"} and not (config / ".initializing").exists():
        raise RuntimeError("Managed database or role missing; recover it before initialization")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", IDENTITY["port"])) == 0 and not managed:
            raise RuntimeError("Configured port is already in use")
    for path in [Path("/opt") / IDENTITY["service_name"], Path(IDENTITY["reader_root"]), Path(IDENTITY["web_root"]), Path("/var/lib") / IDENTITY["service_name"], Path("/var/backups") / IDENTITY["service_name"],
                 Path("/etc/systemd/system") / (IDENTITY["service_name"] + ".service"),
                 Path("/etc/systemd/system") / (IDENTITY["service_name"] + "-backup.service"),
                 Path("/etc/systemd/system") / (IDENTITY["service_name"] + "-backup.timer"),
                 Path("/etc/nginx/snippets") / (IDENTITY["service_name"] + ".conf"),
                 Path("/usr/local/sbin") / (IDENTITY["service_name"] + "-backup")]:
        if path.exists() and not managed:
            raise RuntimeError("Existing deployment path is not managed by this edition")
    if managed:
        if config.stat().st_uid != 0 or config.stat().st_mode & 0o077:
            raise RuntimeError("Protected configuration directory ownership or permissions too broad")
        for name in ["environment", "backup-key"]:
            path = config / name
            if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077 or path.stat().st_uid != 0 or path.stat().st_gid != 0:
                raise RuntimeError("Protected secret missing or permissions too broad: " + name)
        environment = dict(line.split("=", 1) for line in (config / "environment").read_text().splitlines() if line and not line.startswith("#"))
        url = urlsplit(environment.get("DATABASE_URL", ""))
        if (url.scheme != "ecto" or url.hostname != "localhost" or url.username != database or url.path != "/" + database
                or environment.get("PORT") != str(IDENTITY["port"]) or environment.get("GA_BIND_ADDRESS") != "127.0.0.1"):
            raise RuntimeError("Protected environment does not match edition isolation")
        if len(base64.b64decode(environment.get("GA_ACCESS_ENCRYPTION_KEY", ""), validate=True)) != 32:
            raise RuntimeError("Protected message encryption key is invalid")
    run(["nginx", "-t"])
    max_connections = int(postgres("SHOW max_connections;"))
    current_connections = int(postgres("SELECT count(*) FROM pg_stat_activity;"))
    if current_connections + IDENTITY["pool_size"] + 5 >= max_connections:
        raise RuntimeError("PostgreSQL has insufficient connection headroom for another service")
    available_kib = next(int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
    if available_kib < 384 * 1024:
        raise RuntimeError("Host has less than 384 MiB available memory; add capacity before initialization")
    print("Capacity: " + str(available_kib // 1024) + " MiB available; " + str(max_connections - current_connections) + " PostgreSQL connections free. Check capacity for the complete eleven-app fleet before activation.")
    return config, managed, inventory


def apply(release, config, managed, inventory):
    if not release:
        raise RuntimeError("--release is required for --apply")
    os.umask(0o077)
    service, user, database = (IDENTITY[key] for key in ["service_name", "os_user", "database"])
    if not managed:
        config.mkdir(mode=0o700)
        password = secrets.token_urlsafe(32)
        environment = (HERE / "environment.example").read_text()
        environment = environment.replace("REPLACE_DATABASE_PASSWORD", password)
        environment = environment.replace("REPLACE_WITH_MIX_PHX_GEN_SECRET", secrets.token_urlsafe(64))
        environment = environment.replace("REPLACE_WITH_BASE64_OF_32_RANDOM_BYTES", base64.b64encode(secrets.token_bytes(32)).decode())
        private_write(config / "environment", environment)
        private_write(config / "backup-key", secrets.token_urlsafe(64) + "\n")
        private_write(config / "identity.json", json.dumps(IDENTITY, sort_keys=True) + "\n")
        private_write(config / ".initializing", "Interrupted first initialization can resume with the same secrets.\n")
    # Never rotate an existing environment or backup key during an update.
    environment = dict(line.split("=", 1) for line in (config / "environment").read_text().splitlines() if line and not line.startswith("#"))
    if (config / ".initializing").exists():
        try:
            pwd.getpwnam(user)
        except KeyError:
            run(["useradd", "--system", "--user-group", "--no-create-home", "--shell", "/usr/sbin/nologin", user])
        if not postgres("SELECT 1 FROM pg_roles WHERE rolname='" + database + "';"):
            password = urlsplit(environment["DATABASE_URL"]).password
            postgres("CREATE ROLE " + database + " LOGIN PASSWORD '" + password + "';", private=True)
        if not postgres("SELECT 1 FROM pg_database WHERE datname='" + database + "';"):
            run(["runuser", "-u", "postgres", "--", "createdb", "--owner", database, database])
    state = Path("/var/lib") / service
    state.mkdir(mode=0o700, exist_ok=True)
    account = pwd.getpwnam(user)
    os.chown(state, account.pw_uid, account.pw_gid)
    state.chmod(0o700)
    environment.update({"RELEASE_DISTRIBUTION": "none", "RELEASE_MODE": "interactive", "ERL_FLAGS": "+S 1:1 +SDcpu 1 +SDio 1 +A 1", "RELEASE_TMP": str(state), "ERL_CRASH_DUMP": str(state / "erl_crash.dump")})
    # eval must not start an HTTP listener alongside an already running release.
    evaluation_environment = {**os.environ, **environment}
    evaluation_environment.pop("PHX_SERVER", None)
    evaluation_environment.pop("GA_SKIP_REPO", None)
    digest = hashlib.sha256()
    for path in sorted(release.rglob("*")):
        digest.update(path.relative_to(release).as_posix().encode() + b"\0")
        if path.is_symlink():
            digest.update(b"link:" + os.readlink(path).encode())
        elif path.is_file():
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
    release_hash = digest.hexdigest()[:16]
    destination = Path("/opt") / service / "releases" / release_hash
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if not destination.exists():
        shutil.copytree(release, destination, symlinks=True)
        # The source deployment's Erlang cookie is a secret, not shared code.
        # Replace it before making copied release files readable by this user.
        cookie = destination / "releases/COOKIE"
        cookie.unlink(missing_ok=True)
        private_write(cookie, secrets.token_urlsafe(48) + "\n")
        os.chown(cookie, account.pw_uid, account.pw_gid)
    # Release directories must be traversable by this edition's unprivileged user.
    for path in [destination.parent.parent, destination.parent, destination, *destination.rglob("*")]:
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o755)
        elif path == destination / "releases/COOKIE":
            path.chmod(0o600)
        elif path.is_file() and not path.is_symlink():
            path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
    command = ["runuser", "-u", user, "--", str(destination / "bin/ga_server"), "eval", "Ecto.Migrator.with_repo(GA.Repo, fn repo -> Ecto.Migrator.run(repo, :up, all: true) end)"]
    result = subprocess.run(command, env=evaluation_environment, cwd=destination, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Database migration failed; protected output withheld")
    # Erase expired retained data before a restored database can serve requests.
    result = subprocess.run(["runuser", "-u", user, "--", str(destination / "bin/ga_server"), "eval", "Application.ensure_all_started(:ga_server); case GA.Access.prune_private_data() do {:ok, _} -> :ok; _ -> System.halt(1) end"], env=evaluation_environment, cwd=destination, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Post-migration retention failed; protected output withheld")
    current = destination.parent.parent / "current"
    temporary = current.with_name(".current-initializing")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(destination)
    temporary.replace(current)
    for tree in ["reader", "web"]:
        fingerprint = hashlib.sha256((HERE / (tree + "-inventory.json")).read_bytes()).hexdigest()[:16]
        public_root = Path(IDENTITY[tree + "_root"])
        public_destination = public_root / "releases" / fingerprint
        public_destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        if not public_destination.exists():
            shutil.copytree(HERE / tree, public_destination)
        data_inventory = json.loads((HERE / (tree + "-inventory.json")).read_text())
        if public_destination.is_symlink() or any(path.is_symlink() for path in public_destination.rglob("*")):
            raise RuntimeError("Installed public snapshot must not contain symlinks")
        actual = {path.relative_to(public_destination).as_posix() for path in public_destination.rglob("*") if path.is_file()}
        if actual != set(data_inventory["files"]):
            raise RuntimeError("Installed public snapshot inventory mismatch")
        for name, info in data_inventory["files"].items():
            data = (public_destination / name).read_bytes()
            if len(data) != info["bytes"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise RuntimeError("Installed public snapshot integrity failure: " + name)
        for path in [public_root, public_destination.parent, public_destination, *public_destination.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        temporary = public_root / ".current-initializing"
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
        temporary.symlink_to(public_destination)
        temporary.replace(public_root / "current")
    for source, destination in [("access.service", "/etc/systemd/system/" + service + ".service"),
                                ("author-apps.slice", "/etc/systemd/system/author-apps.slice"),
                                ("backup.service", "/etc/systemd/system/" + service + "-backup.service"),
                                ("backup.timer", "/etc/systemd/system/" + service + "-backup.timer"),
                                ("backup.sh", "/usr/local/sbin/" + service + "-backup"),
                                ("nginx.conf", "/etc/nginx/snippets/" + service + ".conf")]:
        shutil.copyfile(HERE / source, destination)
        Path(destination).chmod(0o755 if source == "backup.sh" else 0o644)
    backups = Path("/var/backups") / service
    backups.mkdir(exist_ok=True, mode=0o700)
    backups.chmod(0o700)
    run(["systemctl", "daemon-reload"])
    (config / ".initializing").unlink(missing_ok=True)
    print("Initialized " + service + "; secrets stayed on this host.")
    print("Activate service and backup timer, include its nginx snippet once, validate nginx, then reload.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, help="Existing Linux-built ga_server release to copy; never a macOS release")
    parser.add_argument("--apply", action="store_true", help="Initialize this edition; default is read-only preflight")
    args = parser.parse_args()
    try:
        release = args.release.resolve() if args.release else None
        config, managed, inventory = preflight(release)
        if args.apply:
            apply(release, config, managed, inventory)
        else:
            print("Preflight passed: " + IDENTITY["service_name"] + "; " + str(inventory["downloads"]) + " verified reader downloads. No changes made.")
    except (OSError, ValueError, RuntimeError) as error:
        print("Initialization stopped: " + str(error), file=sys.stderr)
        sys.exit(1)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "editions/authors.json")
    parser.add_argument("--slug", action="append", help="Generate selected editions; repeat for multiple authors")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and report local changes without writing")
    parser.add_argument("--check", action="store_true", help="Fail if checked-in generated files do not match inputs")
    args = parser.parse_args()
    authors = load_authors(args.manifest)
    if args.slug:
        missing = set(args.slug) - {a["slug"] for a in authors}
        if missing:
            raise ValueError("Unknown author slug: " + ", ".join(sorted(missing)))
        authors = [a for a in authors if a["slug"] in args.slug]
    planned = []
    for author in authors:
        edition = args.manifest.resolve().parent / author["slug"]
        planned.append((author, edition / "deploy", generate_files(author, edition)))
    for author, destination, files in planned:
        changed = write_files(destination, files, args.check, args.dry_run)
        action = "checked" if args.check else "planned" if args.dry_run else "generated"
        print(f"{author['slug']}: {action} {len(files)} files ({changed} changed)")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
