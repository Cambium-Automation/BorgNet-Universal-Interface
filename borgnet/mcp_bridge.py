"""Explicit MCP reads/calls and an opt-in, read-only shared context server."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import timedelta
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP


@asynccontextmanager
async def session(source, store, with_capabilities=False):
    if source.transport == "stdio":
        if not source.command:
            raise ValueError("Set an installed MCP command and its argument list")
        # Pass only the SDK's minimal process environment plus the explicitly named variable.
        env = {source.key_env: os.environ[source.key_env]} if source.key_env and source.key_env in os.environ else None
        transport = stdio_client(StdioServerParameters(command=source.command, args=source.args, env=env))
    else:
        if not source.url:
            raise ValueError("Set the MCP Streamable HTTP endpoint")
        key = store.secret(source)
        transport = streamablehttp_client(source.url, headers={"Authorization": f"Bearer {key}"} if key else None,
            timeout=timedelta(seconds=30), sse_read_timeout=timedelta(seconds=90))
    async with transport as streams:
        async with ClientSession(streams[0], streams[1], read_timeout_seconds=timedelta(seconds=90)) as client:
            initialized = await client.initialize()
            yield (client, initialized.capabilities) if with_capabilities else client


async def inspect_source(source, store):
    async with asyncio.timeout(90):
        async with session(source, store, with_capabilities=True) as (client, capabilities):
            tools, resources = [], []
            # Some MCP servers implement only one capability; respect negotiated capabilities.
            # Method-not-found is the only optional-method failure suppressed.
            from mcp.shared.exceptions import McpError
            for method, target, attr in [(client.list_tools, tools, "tools"), (client.list_resources, resources, "resources")]:
                if getattr(capabilities, attr, None) is None:
                    continue
                cursor = None
                try:
                    for _ in range(20):
                        page = await method(cursor=cursor)
                        target.extend(item.model_dump(by_alias=True, mode="json") for item in getattr(page, attr))
                        cursor = page.nextCursor
                        if not cursor:
                            break
                except McpError as error:
                    if error.error.code != -32601:
                        raise
            return {"tools": tools, "resources": resources}


async def fetch_context(source, store, kind, name, arguments):
    async with asyncio.timeout(120):
        async with session(source, store) as client:
            if kind == "resource":
                result = await client.read_resource(name)
            elif kind == "tool":
                result = await client.call_tool(name, arguments)
            else:
                raise ValueError("Choose a tool or resource")
        # Validate after transport cleanup so application errors aren't wrapped in task groups.
        data = result.model_dump(by_alias=True, mode="json")
        if data.get("isError"):
            raise ValueError("MCP tool reported an error; inspect the source server")
        blocks = data.get("contents", data.get("content", []))
        text = "\n".join(block["text"] for block in blocks if isinstance(block.get("text"), str))
        if not text:
            raise ValueError("This result has no text content to attach")
        if len(text) > 100_000:
            raise ValueError("MCP result exceeds 100,000 characters; narrow the query")
        return text


def shared_server(store):
    server = FastMCP("BorgNet shared context")

    @server.tool()
    def list_shared_context() -> list[dict]:
        """List context items explicitly marked Share via MCP by the workspace owner."""
        return [{"id": c["id"], "title": c["title"]} for c in store.read("context", []) if c.get("shared")]

    @server.tool()
    def read_shared_context(context_id: str) -> str:
        """Read one explicitly shared text item. Private entries are never returned."""
        for entry in store.read("context", []):
            if entry["id"] == context_id and entry.get("shared"):
                return entry["text"]
        raise ValueError("Shared context not found")

    @server.resource("borgnet://shared/context")
    def context_index() -> str:
        """The index of explicitly shared items; contains no credentials or endpoint settings."""
        return json.dumps(list_shared_context())

    return server
