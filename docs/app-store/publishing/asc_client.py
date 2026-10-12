"""Small credential-safe App Store Connect client. Never prints key material/JWTs."""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

BASE_URL = "https://api.appstoreconnect.apple.com"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class APIError(RuntimeError):
    def __init__(self, status: int, path: str, detail: str):
        self.status = status
        super().__init__(f"HTTP {status} {path}: {detail}")


class ASCClient:
    def __init__(self, *, allow_writes: bool = False):
        self.allow_writes = allow_writes
        self.key_id = os.environ.get("ASC_KEY_ID")
        path = os.environ.get("ASC_KEY_PATH")
        if not self.key_id or not path:
            raise RuntimeError("Set ASC_KEY_ID and ASC_KEY_PATH; optionally ASC_ISSUER_ID for a team key.")
        self.key = serialization.load_pem_private_key(Path(path).expanduser().read_bytes(), password=None)
        self.issuer = os.environ.get("ASC_ISSUER_ID")

    def token(self) -> str:
        now = int(time.time())
        payload = {"aud": "appstoreconnect-v1", "iat": now, "exp": now + 900}
        payload.update({"iss": self.issuer} if self.issuer else {"sub": "user"})
        header = {"alg": "ES256", "kid": self.key_id, "typ": "JWT"}
        content = ".".join(_b64(json.dumps(x, separators=(",", ":")).encode()) for x in (header, payload)).encode()
        r, s = utils.decode_dss_signature(self.key.sign(content, ec.ECDSA(hashes.SHA256())))
        return content.decode() + "." + _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    def request(self, method: str, path: str, body=None, params=None):
        if method != "GET" and not self.allow_writes:
            raise RuntimeError("Read-only client: mutations require --apply.")
        url = path if path.startswith("https://") else BASE_URL + path
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.appstoreconnect.apple.com":
            raise RuntimeError("Refusing to send Apple credentials to a different origin.")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + self.token(), "Content-Type": "application/json"}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raise APIError(error.code, parsed.path, error.read().decode()) from error

    def collection(self, path: str, params=None):
        """Follow Apple's paging links, retaining included price-point resources."""
        rows, included = [], {}
        while path:
            page = self.request("GET", path, params=params)
            rows.extend(page.get("data", []))
            for item in page.get("included", []):
                included[(item["type"], item["id"])] = item
            path, params = page.get("links", {}).get("next"), None
        return rows, included

    def rows(self, path: str, params=None):
        return self.collection(path, params)[0]

    def write(self, method: str, resource: str, attributes=None, relationships=None, identifier=None, version="v1"):
        data = {"type": resource}
        if identifier:
            data["id"] = identifier
        if attributes is not None:
            data["attributes"] = attributes
        if relationships is not None:
            data["relationships"] = relationships
        path = f"/{version}/{resource}" + (f"/{identifier}" if identifier else "")
        return self.request(method, path, {"data": data})["data"]


def relation(resource: str, identifier: str):
    return {"data": {"type": resource, "id": identifier}}
