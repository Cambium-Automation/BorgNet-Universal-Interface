"""Small, explicit adapters; model identities always come from the user's endpoint."""
import asyncio
import socket
from pathlib import Path
from urllib.parse import urlsplit, quote
import httpx
from .config import Connection
from .cli_text import CLIText, models as cli_models


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
                "-p", str(ssh.port), "-L", f"127.0.0.1:{port}:{ssh.remote_host}:{ssh.remote_port}"] + (["-i", str(Path(ssh.identity_file).expanduser()), "-o", "IdentitiesOnly=yes"] if ssh.identity_file else []) + [target]

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
        self.cli = CLIText()

    async def request(self, item, method, path, payload=None, timeout=None):
        base = await self.tunnels.url(item)
        key = self.store.secret(item)
        if item.kind == "gemini" and urlsplit(base).hostname == "generativelanguage.googleapis.com" and not key:
            raise ValueError("Gemini API key is missing. Open Edit connection and add an AI Studio API key from a Free Tier project with billing disabled.")
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
        async with httpx.AsyncClient(transport=self.transport, timeout=timeout or item.timeout, follow_redirects=False, trust_env=False) as client:
            try:
                response = await client.request(method, base + path, json=payload, headers=headers)
            except httpx.HTTPError:
                raise ValueError("Endpoint unreachable or timed out; check its URL, service, and tunnel.") from None
            if response.is_error or response.is_redirect:
                if item.kind == "gemini":
                    messages = {
                        400: "Gemini rejected the request. Check the API key, model ID, and request options.",
                        401: "Gemini API key was rejected. Replace it in Edit connection.",
                        403: "Gemini API access was denied. Check the key's project and API restrictions.",
                        404: "Gemini model was not found. Discover models and select an available model ID.",
                        429: "Gemini quota or rate limit reached. Wait for the free quota to reset; no paid fallback was used.",
                    }
                    if response.status_code in messages:
                        raise ValueError(messages[response.status_code])
                # Do not reflect upstream bodies: they can contain echoed credentials or private data.
                raise ValueError(f"Provider returned HTTP {response.status_code}. Check authentication, model support, and service logs.")
            try:
                return response.json()
            except ValueError:
                raise ValueError("Provider returned an invalid JSON response") from None

    async def models(self, item):
        if item.kind == "cli":
            return cli_models(item)
        if item.kind == "cohere":
            names, token = set(), ""
            for _ in range(20):
                data = await self.request(item, "GET", "/v1/models?endpoint=chat&page_size=1000" + ("&page_token=" + quote(token, safe="") if token else ""), timeout=20)
                names.update(m["name"] for m in data.get("models", []) if not m.get("is_deprecated"))
                next_token = data.get("next_page_token")
                if not next_token:
                    return sorted(names)
                if next_token == token:
                    break
                token = next_token
            raise ValueError("Model discovery pagination did not finish; enter a model ID manually")
        path = "/api/tags" if item.kind == "ollama" else "/models"
        data = await self.request(item, "GET", path, timeout=20)
        if item.kind == "ollama":
            return sorted({m["name"] for m in data.get("models", [])})
        if item.kind == "gemini":
            return sorted({m["name"].removeprefix("models/") for m in data.get("models", [])
                           if "generateContent" in m.get("supportedGenerationMethods", [])})
        return sorted({m["id"] for m in data.get("data", [])})

    async def chat(self, item, messages, system="", response_schema=None):
        if not item.model:
            raise ValueError("Select a discovered model or enter a model ID first")
        if item.kind == "cli":
            return await self.cli.chat(item, messages, system, response_schema)
        if item.kind == "ollama":
            data = await self.request(item, "POST", "/api/chat", {"model": item.model, "stream": False,
                **({"format": response_schema} if response_schema is not None else {}),
                **{k: v for k, v in item.options.items() if k in {"think", "keep_alive"}},
                "options": {k: v for k, v in item.options.items() if k in {"num_ctx", "num_predict", "num_gpu", "temperature", "top_p", "top_k"}},
                "messages": ([{"role": "system", "content": system}] if system else []) + messages})
            answer = data.get("message", {}).get("content", "")
        elif item.kind == "openai":
            data = await self.request(item, "POST", "/chat/completions", {"model": item.model, "stream": False,
                **{k: v for k, v in item.options.items() if k in {"max_tokens", "max_completion_tokens", "temperature", "top_p", "top_k", "reasoning_effort", "reasoning_format", "thinking_budget_tokens"}},
                "messages": ([{"role": "system", "content": system}] if system else []) + messages})
            choices = data.get("choices", [])
            answer = choices[0].get("message", {}).get("content", "") if choices else ""
            if isinstance(answer, list):
                answer = "\n".join(x.get("text", "") for x in answer if x.get("type") == "text")
        elif item.kind == "responses":
            data = await self.request(item, "POST", "/responses", {
                "model": item.model, "input": messages, "instructions": system,
                "store": False, "stream": False,
                **{k: v for k, v in item.options.items() if k in {"max_output_tokens", "temperature", "top_p", "reasoning"}}})
            if data.get("status") != "completed":
                raise ValueError("Provider response did not complete; check output token limits and model support")
            answer = "\n".join(c.get("text", "") for output in data.get("output", [])
                if output.get("type") == "message" for c in output.get("content", []) if c.get("type") == "output_text")
        elif item.kind == "cohere":
            data = await self.request(item, "POST", "/v2/chat", {
                "model": item.model, "stream": False,
                "messages": ([{"role": "system", "content": system}] if system else []) + messages,
                **{k: v for k, v in item.options.items() if k in {"max_tokens", "temperature", "p", "k", "stop_sequences", "seed"}}})
            if data.get("finish_reason") != "COMPLETE":
                raise ValueError("Provider response did not complete; check output token limits and model support")
            answer = "\n".join(c.get("text", "") for c in data.get("message", {}).get("content", []) if c.get("type") == "text")
        elif item.kind == "anthropic":
            data = await self.request(item, "POST", "/messages", {"model": item.model, "max_tokens": 4096,
                "system": system, "messages": messages,
                **{k: v for k, v in item.options.items() if k in {"max_tokens", "temperature", "top_p", "top_k", "stop_sequences"}}})
            answer = "\n".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
        else:
            payload = {"contents": [{"role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}]} for m in messages]}
            generation = {k: v for k, v in item.options.items() if k in {"maxOutputTokens", "temperature", "topP", "topK", "stopSequences"}}
            if generation:
                payload["generationConfig"] = generation
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
