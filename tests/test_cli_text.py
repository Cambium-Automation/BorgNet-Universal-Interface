import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from borgnet import cli_text
from borgnet.config import Connection, Store
from borgnet.providers import Providers, Tunnels


def item(provider="grok", **kwargs):
    return Connection(kind="cli", cli_provider=provider, url="http://127.0.0.1", model="default", **kwargs)


def test_cli_configuration():
    assert item("codex").address == "Codex CLI · this computer"
    with pytest.raises(ValidationError):
        item("codex", cli_agent="test")
    with pytest.raises(ValidationError):
        item(cli_agent="../../evil")
    with pytest.raises(ValidationError):
        item(key_env="TOKEN")


def test_only_final_answer_is_returned(tmp_path):
    assert cli_text.answer("grok", json.dumps({"text": "answer", "thought": "private"}), tmp_path) == "answer"
    assert cli_text.answer("gemini", json.dumps({"response": "answer", "stats": {}}), tmp_path) == "answer"
    with pytest.raises(ValueError, match="no final answer"):
        cli_text.answer("grok", '{"thought":"private"}', tmp_path)


def test_commands_keep_prompts_out_of_shell(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_text, "executable", lambda provider: provider)
    for provider in cli_text.NAMES:
        argv, data = cli_text.command(item(provider), tmp_path, 'literal $(touch injected)')
        assert argv[0] == provider
        assert "--model" not in argv
        if provider == "codex":
            assert data == b'literal $(touch injected)'
        if provider == "grok":
            assert argv[argv.index("--tools") + 1] == ""


@pytest.mark.asyncio
async def test_cli_dispatch_and_exit_errors(monkeypatch, tmp_path):
    script = tmp_path / "fixture"
    script.write_text('#!/bin/sh\nprintf \'{"text":"CONNECTED","thought":"hidden"}\'\n')
    script.chmod(0o755)
    monkeypatch.setattr(cli_text, "executable", lambda _: str(script))
    providers = Providers(Store(tmp_path / "data"), Tunnels())
    assert await providers.chat(item(), [{"role": "user", "content": "hello"}]) == "CONNECTED"
    script.write_text('#!/bin/sh\necho SECRET >&2\nexit 41\n')
    with pytest.raises(ValueError, match="code 41") as error:
        await providers.chat(item(), [])
    assert "SECRET" not in str(error.value)


@pytest.mark.asyncio
async def test_output_bound_stops_cli(monkeypatch, tmp_path):
    script = tmp_path / "flood"
    script.write_text('#!/bin/sh\nwhile :; do printf "0123456789abcdef"; done\n')
    script.chmod(0o755)
    monkeypatch.setattr(cli_text, "executable", lambda _: str(script))
    monkeypatch.setattr(cli_text, "LIMIT", 512)
    with pytest.raises(ValueError, match="size limit"):
        await asyncio.wait_for(cli_text.CLIText().chat(item(), [], "", None), 5)
