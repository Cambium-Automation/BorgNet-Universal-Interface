"""Synthetic HTTP MCP server, launched only by integration tests."""
import sys
from mcp.server.fastmcp import FastMCP
server = FastMCP('BorgNet test fixture', host='127.0.0.1', port=int(sys.argv[1]))

@server.tool()
def read_fixture() -> str:
    """Return a fixed test reference."""
    return 'HTTP MCP fixture text'

@server.resource('fixture://reference')
def reference() -> str:
    return 'HTTP MCP fixture reference'

server.run(transport='streamable-http')
