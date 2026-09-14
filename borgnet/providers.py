"""Small, explicit adapters; model identities always come from the user's endpoint."""
import asyncio
import socket
from urllib.parse import urlsplit, quote
import httpx
from .config import Connection


class Tunnels:
    def __init__(self):
        self.processes = {}
        self.lock = asyncio.Lock()

    @staticmethod
    def command(ssh, port):
        target = f"{ssh.user}@{ssh.host}" if ssh.user else ssh.host
        return ["ssh", "-N", "-T", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
                "-p", str(ssh.port), "-L", f"127.0.0.1:{port}:127.0.0.1:{ssh.remote_port}", target]

    async def url(self, item):
        if not item.ssh:
            return item.url
        async with self.lock:
            existing = self.processes.get(item.id)
            if existing and existing[0].returncode is None:
                return existing[1]
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            process = await asyncio.create_subprocess_exec(*self.command(item.ssh, port),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            url = f"http://127.0.0.1:{port}{urlsplit(item.url).path}"
            self.processes[item.id] = (process, url)
            for _ in range(60):
                if process.returncode is not None:
                    break
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    return url
                except OSError:
                    await asyncio.sleep(.2)
            await self.stop(item.id)
            raise ValueError("SSH tunnel failed. Verify SSH agent/key access and known_hosts with your SSH client first.")

    async def stop(self, identity):
        existing = self.processes.pop(identity, None)
        if existing and existing[0].returncode is None:
            existing[0].terminate()
            try:
                await asyncio.wait_for(existing[0].wait(), 5)
            except TimeoutError:
                existing[0].kill()
                await existing[0].wait()

    async def close(self):
        for identity in list(self.processes):
            await self.stop(identity)


class Providers:
    def __init__(self, store, tunnels, transport=None):
        self.store, self.tunnels, self.transport = store, tunnels, transport

    async def request(self, item, method, path, payload=None, timeout=180):
        base = await self.tunnels.url(item)
        key = self.store.secret(item)
        headers = {}
        if item.kind == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            if key:
                headers["x-api-key"] = key
        elif item.kind == "gemini":
            if key:
                headers["x-goog-api-key"] = key
        elif key:
            headers["Authorization"] = f"Bearer {key}"
        async with httpx.AsyncClient(transport=self.transport, timeout=timeout, follow_redirects=False, trust_env=False) as client:
            try:
                response = await client.request(method, base + path, json=payload, headers=headers)
            except httpx.HTTPError:
                raise ValueError("Endpoint unreachable or timed out; check its URL, service, and tunnel.") from None
            if response.is_error or response.is_redirect:
                # Do not reflect upstream bodies: they can contain echoed credentials or private data.
                raise ValueError(f"Provider returned HTTP {response.status_code}. Check authentication, model support, and service logs.")
            try:
                return response.json()
            except ValueError:
                raise ValueError("Provider returned an invalid JSON response") from None

    async def models(self, item):
        path = "/api/tags" if item.kind == "ollama" else "/models"
        data = await self.request(item, "GET", path, timeout=20)
        if item.kind == "ollama":
            return sorted({m["name"] for m in data.get("models", [])})
        if item.kind == "gemini":
            return sorted({m["name"].removeprefix("models/") for m in data.get("models", [])
                           if "generateContent" in m.get("supportedGenerationMethods", [])})
        return sorted({m["id"] for m in data.get("data", [])})

    async def chat(self, item, messages, system=""):
        if not item.model:
            raise ValueError("Select a discovered model or enter a model ID first")
        if item.kind == "ollama":
            data = await self.request(item, "POST", "/api/chat", {"model": item.model, "stream": False,
                "messages": ([{"role": "system", "content": system}] if system else []) + messages})
            answer = data.get("message", {}).get("content", "")
        elif item.kind == "openai":
            data = await self.request(item, "POST", "/chat/completions", {"model": item.model, "stream": False,
                "messages": ([{"role": "system", "content": system}] if system else []) + messages})
            choices = data.get("choices", [])
            answer = choices[0].get("message", {}).get("content", "") if choices else ""
            if isinstance(answer, list):
                answer = "\n".join(x.get("text", "") for x in answer if x.get("type") == "text")
        elif item.kind == "anthropic":
            data = await self.request(item, "POST", "/messages", {"model": item.model, "max_tokens": 4096,
                "system": system, "messages": messages})
            answer = "\n".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
        else:
            payload = {"contents": [{"role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}]} for m in messages]}
            if system:
                payload["systemInstruction"] = {"parts": [{"text": system}]}
            data = await self.request(item, "POST", f"/models/{quote(item.model, safe='')}:generateContent", payload)
            candidates = data.get("candidates", [])
            answer = "\n".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", [])
                               if not p.get("thought")) if candidates else ""
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Model returned no public text answer")
        return answer

    async def pull(self, item, model):
        if item.kind != "ollama":
            raise ValueError("Model downloads are supported by Ollama endpoints only")
        return await self.request(item, "POST", "/api/pull", {"model": model, "stream": False}, timeout=3600)
