"""Text-only connections using an installed CLI's existing sign-in."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile

NAMES = {"codex": "Codex", "grok": "Grok", "gemini": "Gemini", "copilot": "Copilot"}
LIMIT = 1024 * 1024


def executable(provider):
    found = shutil.which(provider)
    if not found:
        raise ValueError(f"{NAMES[provider]} CLI is not installed on this computer or is missing from PATH")
    return found


def models(item):
    executable(item.cli_provider)
    # CLI defaults are account-dependent; do not invent a provider model catalog.
    return list(dict.fromkeys(["default", *([item.model] if item.model else [])]))


def command(item, job, prompt):
    provider = item.cli_provider
    argv = [executable(provider)]
    model = ["--model", item.model] if item.model != "default" else []
    if provider == "codex":
        argv += ["exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                 "--sandbox", "read-only", "--disable", "shell_tool", "--disable", "plugins",
                 "--color", "never", "--output-last-message", str(job / "answer.txt"),
                 *model, "-"]
        return argv, prompt.encode()
    if provider == "grok":
        path = job / "prompt.txt"
        path.write_text(prompt)
        argv += ["--output-format", "json", "--max-turns", "1", "--no-plan",
                 "--no-subagents", "--disable-web-search", "--tools", "",
                 "--permission-mode", "dontAsk", *model, "--prompt-file", str(path)]
        if item.cli_agent:
            argv += ["--agent", item.cli_agent]
    elif provider == "gemini":
        policy = job / "text-only.toml"
        policy.write_text('[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 999\n')
        argv += ["--output-format", "json", "--admin-policy", str(policy),
                 "--extensions", "none", *model, "--prompt", prompt]
    else:
        argv += ["--available-tools=", "--disable-builtin-mcps", "--no-custom-instructions",
                 "--no-ask-user", "--no-auto-update", "--no-remote", "--no-remote-export",
                 "--no-color", "--silent", *model, "--prompt", prompt]
    return argv, b""


def answer(provider, output, job):
    try:
        if provider == "codex":
            path = job / "answer.txt"
            if path.stat().st_size > LIMIT:
                raise ValueError("CLI response exceeded the size limit")
            text = path.read_text()
        elif provider in {"grok", "gemini"}:
            result = json.loads(output)
            if result.get("error"):
                raise ValueError("CLI reported a failure; check its sign-in and usage allowance in your terminal")
            text = result.get("text" if provider == "grok" else "response", "")
        else:
            text = output.decode("utf-8", errors="replace")
    except (OSError, json.JSONDecodeError, AttributeError):
        raise ValueError("CLI did not return a readable final answer") from None
    if not isinstance(text, str) or not text.strip():
        raise ValueError("CLI returned no final answer; check its sign-in and model selection in your terminal")
    return text.strip()


async def bounded_read(stream):
    chunks, size = [], 0
    while chunk := await stream.read(65536):
        size += len(chunk)
        if size > LIMIT:
            raise ValueError("CLI output exceeded the size limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def stop(process):
    # Descendants can retain pipes even after the CLI parent has exited.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if process.returncode is None:
        try:
            await asyncio.wait_for(process.wait(), 2)
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()


class CLIText:
    def __init__(self):
        self.locks = {}

    async def chat(self, item, messages, system, response_schema):
        prompt = "Answer the supplied conversation as a text-only BorgNet participant. Do not use tools.\n"
        prompt += json.dumps({"system": system, "messages": messages}, ensure_ascii=False)
        if response_schema is not None:
            prompt += "\nReturn only JSON matching this schema:\n" + json.dumps(response_schema)
        if len(prompt.encode()) > 100000:
            raise ValueError("Conversation is too large for this CLI connection; shorten the attached context")
        async with self.locks.setdefault(item.cli_provider, asyncio.Lock()):
            with tempfile.TemporaryDirectory(prefix="borgnet-cli-") as directory:
                job = Path(directory)
                argv, data = command(item, job, prompt)
                process = await asyncio.create_subprocess_exec(*argv, cwd=job,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, start_new_session=True)
                async def exchange():
                    async def write():
                        try:
                            process.stdin.write(data)
                            await process.stdin.drain()
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        finally:
                            process.stdin.close()
                    tasks = [asyncio.create_task(coro) for coro in (
                        bounded_read(process.stdout), bounded_read(process.stderr), write(), process.wait())]
                    try:
                        return await asyncio.gather(*tasks)
                    finally:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                try:
                    output, _, _, code = await asyncio.wait_for(exchange(), item.timeout)
                    if code:
                        raise ValueError(f"{NAMES[item.cli_provider]} CLI exited with code {code}; open `{item.cli_provider}` in your terminal to check sign-in, model access, or usage limits")
                    return answer(item.cli_provider, output, job)
                except TimeoutError:
                    raise ValueError(f"{NAMES[item.cli_provider]} CLI timed out") from None
                finally:
                    await stop(process)
