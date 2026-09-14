"""Text-only connections using an installed CLI's existing sign-in."""
import asyncio
import json
import codecs
import os
import sys
import time
import subprocess
import re
from pathlib import Path
import shutil
import signal
import tempfile
from .permissions import Policy, instructions

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


def command(item, job, prompt, policy=None):
    policy = policy or Policy()
    provider = item.cli_provider
    argv = [executable(provider)]
    model = ["--model", item.model] if item.model != "default" else []
    if provider == "codex":
        argv += ["exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                 "--sandbox", "read-only", "--disable", "shell_tool", "--disable", "plugins",
                 "--color", "never", "--output-last-message", str(job / "answer.txt"),
                 *model, "-"]
        if policy.full_access:
            i = argv.index('--sandbox'); del argv[i:i+2]
            i = argv.index('shell_tool'); del argv[i-1:i+1]
            argv.insert(1, '--dangerously-bypass-approvals-and-sandbox')
        if policy.network or policy.full_access:
            argv.insert(1, '--search')
        return argv, prompt.encode()
    if provider == "grok":
        path = job / "prompt.txt"
        path.write_text(prompt)
        argv += ["--output-format", "json", "--max-turns", "1", "--no-plan",
                 "--no-subagents", "--disable-web-search", "--tools", "",
                 "--permission-mode", "dontAsk", "--deny", "MCPTool", *model, "--prompt-file", str(path)]
        if item.cli_agent:
            argv += ["--agent", item.cli_agent]
    elif provider == "gemini":
        policy_file = job / "text-only.toml"
        policy_file.write_text('[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 999\n')
        argv += ["--output-format", "json", "--admin-policy", str(policy_file),
                 "--extensions", "none", *model, "--prompt", prompt]
    else:
        argv += ["--available-tools=", "--disable-builtin-mcps", "--no-custom-instructions",
                 "--no-ask-user", "--no-auto-update", "--no-remote", "--no-remote-export",
                 "--no-color", "--silent", *model, "--prompt", prompt]
    if provider == 'grok' and (policy.network or policy.full_access):
        argv.remove('--disable-web-search')
        argv[argv.index('--max-turns') + 1] = '20'
        argv[argv.index('--tools') + 1] = 'web_search,web_fetch'
        argv += ['--allow', 'WebFetch']
        if policy.full_access:
            i = argv.index('--tools'); del argv[i:i+2]
            argv[argv.index('--permission-mode') + 1] = 'bypassPermissions'
            argv += ['--sandbox', 'off']
    elif provider == 'copilot' and policy.full_access:
        argv.remove('--available-tools=')
        argv += ['--allow-all']
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
    """Terminate the job's process group, including children surviving their parent."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        if process.returncode is None:
            await asyncio.wait_for(process.wait(), 2)
    except TimeoutError:
        pass
    finally:
        # A completed parent does not imply its descendants honored SIGTERM.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.returncode is None:
        await process.wait()


class CLIText:
    def __init__(self):
        self.locks = {}

    async def chat(self, item, messages, system, response_schema, on_delta=None, policy=None):
        policy = policy or Policy()
        prompt = instructions(policy) + "Verify machine facts before stating them.\n"
        prompt += json.dumps({"system": system, "messages": messages}, ensure_ascii=False)
        if response_schema is not None:
            prompt += "\nReturn only JSON matching this schema:\n" + json.dumps(response_schema)
        if len(prompt.encode()) > 100000:
            raise ValueError("Conversation is too large for this CLI connection; shorten the attached context")
        async with self.locks.setdefault(item.cli_provider, asyncio.Lock()):
            with tempfile.TemporaryDirectory(prefix="borgnet-cli-") as directory:
                job = Path(directory)
                argv, data = command(item, job, prompt, policy)
                env = os.environ.copy()
                env.pop("BORGNET_AUTOMATION_GRANT", None)
                if policy.full_access and (policy.browser or policy.computer):
                    argv, env = automation_command(item, job, argv, env, policy)
                streaming = on_delta is not None and item.cli_provider in {'grok', 'copilot'}
                if streaming and item.cli_provider == 'grok':
                    argv[argv.index('--output-format') + 1] = 'streaming-json'
                elif streaming:
                    argv += ['--stream', 'on']
                public = []
                async def read_public(stream):
                    size, pending = 0, ''
                    decoder = codecs.getincrementaldecoder('utf-8')()
                    async def line(text):
                        if not text.strip(): return
                        try: event = json.loads(text)
                        except ValueError: raise ValueError('CLI returned invalid stream JSON') from None
                        if event.get('type') == 'error': raise ValueError('CLI stream failed; check sign-in and quota')
                        if event.get('type') == 'text' and isinstance(event.get('data'), str):
                            public.append(event['data'])
                            await on_delta(event['data'])
                    while chunk := await stream.read(4096):
                        size += len(chunk)
                        if size > LIMIT: raise ValueError('CLI output exceeded the size limit')
                        decoded = decoder.decode(chunk)
                        if item.cli_provider == 'copilot':
                            if decoded:
                                public.append(decoded)
                                await on_delta(decoded)
                        else:
                            pending += decoded
                            while '\n' in pending:
                                value, pending = pending.split('\n', 1)
                                await line(value)
                    tail = decoder.decode(b'', final=True)
                    if item.cli_provider == 'grok':
                        await line(pending + tail)
                    elif tail:
                        public.append(tail)
                        await on_delta(tail)
                    return b''

                process = await asyncio.create_subprocess_exec(*argv, cwd=policy.workspace if policy.full_access else job,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, start_new_session=True, env=env)
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
                        (read_public(process.stdout) if streaming else bounded_read(process.stdout)), bounded_read(process.stderr), write(), process.wait())]
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
                    if streaming:
                        text = ''.join(public).strip()
                        if not text: raise ValueError('CLI returned no public text')
                        return text
                    text = answer(item.cli_provider, output, job)
                    if on_delta is not None:
                        await on_delta(text)
                    return text
                except TimeoutError:
                    raise ValueError(f"{NAMES[item.cli_provider]} CLI timed out") from None
                finally:
                    await stop(process)


def automation_command(item, job, argv, env, policy):
    from .adapter_setup import entrypoint, grok_registered
    grant = job / 'automation-grant.json'
    grant.write_text(json.dumps({'browser':policy.browser,'computer':policy.computer,
                                 'expires':time.time()+min(item.timeout,1800)}))
    grant.chmod(0o600)
    env['BORGNET_AUTOMATION_GRANT']=str(grant)
    server={'command':sys.executable,'args':[entrypoint()],
            'env':{'BORGNET_AUTOMATION_GRANT':str(grant)}}
    if item.cli_provider=='codex':
        # CLI overrides are scoped to this invocation; the user's global config stays untouched.
        for key,value in {**server,'enabled':True,'required':True,'startup_timeout_sec':30,'tool_timeout_sec':45,'default_tools_approval_mode':'auto'}.items():
            if isinstance(value,dict):
                literal='{'+', '.join(k+'='+json.dumps(v) for k,v in value.items())+'}'
            else:literal=json.dumps(value)
            argv[1:1]=['-c','mcp_servers.borgnet_automation.'+key+'='+literal]
    elif item.cli_provider=='copilot':
        argv+=['--additional-mcp-config',json.dumps({'mcpServers':{'borgnet_automation':{**server,'type':'local','tools':['*']}}})]
    elif item.cli_provider=='grok':
        if not grok_registered():raise ValueError('Run borgnet adapters install to register the gated Grok adapter.')
        listed=subprocess.run([argv[0],'mcp','list','--json'],capture_output=True,text=True,timeout=15,check=True)
        servers=json.loads(listed.stdout)
        if not isinstance(servers,list):raise ValueError('Grok MCP inventory is not readable; adapter access refused.')
        names=[]
        for server in servers:
            name=server.get('name','')
            if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('Grok MCP inventory contains an unsupported name; adapter access refused.')
            names.append(name)
        index=argv.index('--deny');del argv[index:index+2]
        for name in names:
            if name!='borgnet_automation':argv+=['--deny',f'MCPTool({name}__*)']
        argv+=['--allow','MCPTool(borgnet_automation__*)']
    return argv,env
