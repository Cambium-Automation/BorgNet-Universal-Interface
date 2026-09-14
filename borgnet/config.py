"""User-owned state. Nothing is provisioned or contacted on first launch."""
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, field_validator


MAX_CONNECTIONS = 50

def endpoint(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Use an HTTP(S) base URL without credentials, query, or fragment")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Use HTTPS for remote endpoints, or an SSH tunnel to a loopback URL")
    return value.rstrip("/")


class SSH(BaseModel):
    host: str = Field(min_length=1, max_length=253, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    user: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$|^$")
    port: int = Field(default=22, ge=1, le=65535)
    remote_port: int = Field(default=11434, ge=1, le=65535)

    remote_host: str = Field(default="127.0.0.1", max_length=253, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    identity_file: str = Field(default="", max_length=1000)

    @property
    def address(self):
        return f"{self.user + '@' if self.user else ''}{self.host}:{self.port}"


class Connection(BaseModel):
    id: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_-]*$")
    kind: Literal["ollama", "openai", "anthropic", "gemini"] = "ollama"
    url: str
    purpose: str = Field(default="", max_length=4000)
    model: str = Field(default="", max_length=300)
    enabled: bool = True
    key_env: str = Field(default="", max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$|^$")
    ssh: SSH | None = None
    options: dict = Field(default_factory=dict)
    model_options: dict[str, dict] = Field(default_factory=dict)
    timeout: int = Field(default=180, ge=10, le=1800)
    _url = field_validator("url")(endpoint)

    @property
    def address(self):
        return self.ssh.address if self.ssh else self.url


class MCPSource(BaseModel):
    id: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    transport: Literal["http", "stdio"] = "http"
    url: str = ""
    command: str = Field(default="", max_length=1000)
    args: list[str] = Field(default_factory=list, max_length=64)
    key_env: str = Field(default="", max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$|^$")

    @field_validator("url")
    @classmethod
    def check_url(cls, value):
        return endpoint(value) if value else ""


class Store:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()

    def read(self, name, default):
        with self.lock:
            path = self.root / f"{name}.json"
            return json.loads(path.read_text()) if path.exists() else default

    def write(self, name, value):
        with self.lock:
            fd, temp = tempfile.mkstemp(dir=self.root, prefix=".write-")
            try:
                with os.fdopen(fd, "w") as output:
                    json.dump(value, output, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, self.root / f"{name}.json")
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)

    def config(self):
        return self.read("config", {"connections": [], "mcp_sources": [], "theme": "system", "synthesis": ""})

    def secret(self, item):
        return os.environ.get(item.key_env, "") if item.key_env else self.read("secrets", {}).get(item.id, "")

    def save_secret(self, identity, value):
        with self.lock:
            keys = self.read("secrets", {})
            if value:
                keys[identity] = value
            else:
                keys.pop(identity, None)
            self.write("secrets", keys)

    def append(self, name, value, limit=100):
        with self.lock:
            entries = self.read(name, [])
            entries.append(value)
            self.write(name, entries[-limit:])
