import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="BorgNet Universal Interface")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("BORGNET_DATA_DIR", "~/.borgnet")))
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start the local workspace")
    serve.add_argument("--port", type=int, default=7337)
    sub.add_parser("mcp", help="Expose only explicitly shared context over MCP stdio")
    adapters = sub.add_parser("adapters", help="Install or inspect browser and desktop adapters")
    adapters.add_argument("action", choices=["install", "status"])
    args = parser.parse_args()
    if args.command == "adapters":
        import json
        from .adapter_setup import install, status
        if args.action == "install":
            install()
        else:
            print(json.dumps(status(), indent=2))
    elif args.command == "mcp":
        from .config import Store
        from .mcp_bridge import shared_server
        shared_server(Store(args.data_dir)).run(transport="stdio")
    else:
        import uvicorn
        from .server import create_app
        app = create_app(args.data_dir)
        print(f"Open your private workspace: http://127.0.0.1:{args.port}/#session={app.state.session_token}", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
