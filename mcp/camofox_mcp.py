#!/usr/bin/env python3
"""
camofox-mcp — MCP server wrapper for camofox-browser REST API.

Exposes all camofox tools as MCP tools so opencode/other MCP clients can
use the full camofox browser automation toolkit.

Usage:
    # Standalone (starts camofox server if needed):
    python3 camofox_mcp.py

    # With opencode:
    opencode mcp add camofox -- python3 /path/to/camofox_mcp.py
"""
import os
import sys
import json
import asyncio
import logging
import subprocess
import time
import tempfile
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("httpx required: pip install httpx", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("camofox-mcp")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CAMOFOX_HOST = os.environ.get("CAMOFOX_HOST", "localhost")
CAMOFOX_PORT = int(os.environ.get("CAMOFOX_PORT", "9377"))
CAMOFOX_BASE = f"http://{CAMOFOX_HOST}:{CAMOFOX_PORT}"
CAMOFOX_SERVER_DIR = os.environ.get("CAMOFOX_SERVER_DIR", "/var/home/bazzite/camofox-browser")
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "")
# If AUTO_START is "1", the MCP will try to start the camofox server itself.
# This requires ./run.sh to be executable and port 9377 to be available.
# Start the server manually with: cd /var/home/bazzite/camofox-browser && ./run.sh
CAMOFOX_AUTO_START = os.environ.get("CAMOFOX_AUTO_START", "0") == "1"

# ---------------------------------------------------------------------------
# Camofox server lifecycle
# ---------------------------------------------------------------------------
_camofox_running = None

def is_camofox_running() -> bool:
    try:
        r = httpx.get(f"{CAMOFOX_BASE}/health", timeout=3)
        return r.is_success
    except Exception:
        return False

async def is_camofox_running_async() -> bool:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{CAMOFOX_BASE}/health", timeout=3)
            return r.is_success
    except Exception:
        return False

def ensure_camofox_server():
    """
    Start the camofox server if not already running and CAMOFOX_AUTO_START=1.
    Otherwise just check if it's already running.
    Sets module-level flag so we only try once per process.
    """
    global _camofox_running
    if _camofox_running is not None:
        return _camofox_running

    if is_camofox_running():
        logger.info("camofox server already running at %s", CAMOFOX_BASE)
        _camofox_running = True
        return True

    if not CAMOFOX_AUTO_START:
        logger.info("camofox server not running at %s — set CAMOFOX_AUTO_START=1 to auto-launch", CAMOFOX_BASE)
        _camofox_running = False
        return False

    logger.info("camofox server not running — starting at %s", CAMOFOX_BASE)

    server_script = Path(CAMOFOX_SERVER_DIR) / "run.sh"
    if not server_script.exists():
        logger.error("run.sh not found at %s", server_script)
        _camofox_running = False
        return False

    env = {**os.environ, "CAMOFOX_PORT": str(CAMOFOX_PORT)}
    if CAMOFOX_API_KEY:
        env["CAMOFOX_API_KEY"] = CAMOFOX_API_KEY

    try:
        proc = subprocess.Popen(
            [str(server_script)],
            cwd=str(server_script.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.error("Failed to start camofox server: %s", e)
        _camofox_running = False
        return False

    # Poll for up to 60 seconds
    for i in range(60):
        time.sleep(1)
        if is_camofox_running():
            logger.info("camofox server ready on port %s (pid %s)", CAMOFOX_PORT, proc.pid)
            _camofox_running = True
            return True

    logger.error("camofox server failed to start within 60s")
    proc.kill()
    _camofox_running = False
    return False

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
async def api_get(path: str, params: dict | None = None, timeout: float = 30) -> dict:
    async with httpx.AsyncClient(base_url=CAMOFOX_BASE, timeout=timeout) as client:
        r = await client.get(path, params=params)
        r.raise_for_status()
        return r.json()

async def api_post(path: str, json: dict | None = None, timeout: float = 30) -> dict:
    async with httpx.AsyncClient(base_url=CAMOFOX_BASE, timeout=timeout) as client:
        r = await client.post(path, json=json)
        r.raise_for_status()
        return r.json()

async def api_delete(path: str, json: dict | None = None, timeout: float = 30) -> dict:
    async with httpx.AsyncClient(base_url=CAMOFOX_BASE, timeout=timeout) as client:
        r = await client.delete(path, json=json)
        r.raise_for_status()
        return r.json()

def auth_headers() -> dict:
    if CAMOFOX_API_KEY:
        return {"Authorization": f"Bearer {CAMOFOX_API_KEY}"}
    return {}

# ---------------------------------------------------------------------------
# MCP Tool definitions
# ---------------------------------------------------------------------------
TOOLS = []

def _t(name: str, desc: str, input_schema: dict) -> dict:
    """Define an MCP tool."""
    TOOL = {
        "name": name,
        "description": desc,
        "inputSchema": input_schema,
    }
    TOOLS.append(TOOL)
    return TOOL

# Tool: health_check
_t("health_check", "Check if the camofox server is running and healthy.", {
    "type": "object",
    "properties": {},
})

# Tool: create_tab
_t("create_tab", "Create a new browser tab in camofox. Returns tabId needed for subsequent operations.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Initial URL to navigate to"},
        "userId": {"type": "string", "description": "User ID for session isolation (default: camofox-default)"},
        "sessionKey": {"type": "string", "description": "Groups tabs by conversation/session (default: default)"},
    },
    "required": ["url"],
})

# Tool: open_tab (convenience: create + navigate in one request)
_t("open_tab", "Create a new tab and navigate to URL in one atomic request. Faster than separate create_tab + navigate calls.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to open"},
        "userId": {"type": "string"},
        "sessionKey": {"type": "string", "description": "Session group key (default: default)"},
    },
    "required": ["url"],
})

# Tool: navigate
_t("navigate", "Navigate to a URL or expand a search macro (@google_search, @perplexity_search, etc.)", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string", "description": "Tab identifier from create_tab"},
        "url": {"type": "string", "description": "Direct URL to navigate to"},
        "macro": {"type": "string", "description": "Search macro name (e.g. @google_search, @perplexity_search)"},
        "query": {"type": "string", "description": "Search query (used with macro)"},
        "userId": {"type": "string"},
    },
    "required": ["tabId"],
})

# Tool: snapshot
_t("snapshot", "Get accessibility snapshot of page with element refs (e1, e2...). Includes screenshot by default.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "userId": {"type": "string"},
        "offset": {"type": "integer", "description": "Pagination offset for large pages (use nextOffset from previous response)"},
    },
    "required": ["tabId"],
})

# Tool: click
_t("click", "Click an element by ref (e1, e2...) or CSS selector. Use doubleClick=true to double-click.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "ref": {"type": "string", "description": "Element ref from snapshot (e.g. e1)"},
        "selector": {"type": "string", "description": "CSS selector (alternative to ref)"},
        "doubleClick": {"type": "boolean", "description": "Perform a double-click (default: false)"},
        "userId": {"type": "string"},
    },
    "required": ["tabId"],
})

# Tool: type_text
_t("type_text", "Type text into an element. Set submit=true to press Enter after typing.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "ref": {"type": "string"},
        "selector": {"type": "string"},
        "text": {"type": "string"},
        "submit": {"type": "boolean", "description": "Press Enter after typing (default: false)"},
        "userId": {"type": "string"},
    },
    "required": ["tabId", "text"],
})

# Tool: scroll
_t("scroll", "Scroll the page.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
        "amount": {"type": "integer", "description": "Pixels to scroll (default: 500)"},
        "userId": {"type": "string"},
    },
    "required": ["tabId", "direction"],
})

# Tool: screenshot
_t("screenshot", "Take a PNG screenshot of the current page.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "fullPage": {"type": "boolean", "description": "Capture entire scrollable page (default: false)"},
        "userId": {"type": "string"},
    },
    "required": ["tabId"],
})

# Tool: links
_t("links", "Extract all HTTP links from the page.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "limit": {"type": "integer", "default": 50},
        "offset": {"type": "integer", "default": 0},
        "userId": {"type": "string"},
    },
    "required": ["tabId"],
})

# Tool: images
_t("images", "Extract img element metadata from the page.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "includeData": {"type": "boolean", "description": "Include inline data URLs"},
        "limit": {"type": "integer", "default": 8},
        "userId": {"type": "string"},
    },
    "required": ["tabId"],
})

# Tool: downloads
_t("downloads", "List captured browser downloads.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "includeData": {"type": "boolean"},
        "consume": {"type": "boolean", "description": "Clear downloads after reading"},
        "userId": {"type": "string"},
    },
    "required": ["tabId"],
})

# Tool: evaluate
_t("evaluate", "Execute JavaScript in the page context. Returns the JS result.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "expression": {"type": "string", "description": "JavaScript expression"},
        "userId": {"type": "string"},
    },
    "required": ["tabId", "expression"],
})

# Tool: wait
_t("wait", "Wait for a CSS selector to appear or timeout.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "selector": {"type": "string"},
        "timeout": {"type": "integer", "description": "ms (default: 15000)"},
        "userId": {"type": "string"},
    },
    "required": ["tabId"],
})

# Tool: press
_t("press", "Press a keyboard key (Enter, Tab, Escape, ArrowDown...)", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "key": {"type": "string"},
        "userId": {"type": "string"},
    },
    "required": ["tabId", "key"],
})

# Tool: back / forward / refresh
_t("back", "Navigate back in browser history.", {
    "type": "object",
    "properties": {"tabId": {"type": "string"}, "userId": {"type": "string"}},
    "required": ["tabId"],
})

_t("forward", "Navigate forward in browser history.", {
    "type": "object",
    "properties": {"tabId": {"type": "string"}, "userId": {"type": "string"}},
    "required": ["tabId"],
})

_t("refresh", "Reload the current page.", {
    "type": "object",
    "properties": {"tabId": {"type": "string"}, "userId": {"type": "string"}},
    "required": ["tabId"],
})

# Tool: stats
_t("stats", "Get tab statistics (visited URLs, tool calls, download count).", {
    "type": "object",
    "properties": {"tabId": {"type": "string"}, "userId": {"type": "string"}},
    "required": ["tabId"],
})

# Tool: list_tabs
_t("list_tabs", "List all open browser tabs.", {
    "type": "object",
    "properties": {"userId": {"type": "string"}},
})

# Tool: close_tab
_t("close_tab", "Close a specific browser tab.", {
    "type": "object",
    "properties": {"tabId": {"type": "string"}, "userId": {"type": "string"}},
    "required": ["tabId"],
})

# Tool: close_session
_t("close_session", "Close all tabs for a user session.", {
    "type": "object",
    "properties": {"userId": {"type": "string"}},
    "required": ["userId"],
})

# Tool: act (unified action dispatcher)
_t("act", "Unified action dispatcher: click, type, press, or scroll via /act endpoint. Auto-refreshes stale element refs before acting. Prefer this over individual tools when the ref might be stale.", {
    "type": "object",
    "properties": {
        "tabId": {"type": "string"},
        "kind": {"type": "string", "enum": ["click", "type", "press", "scroll", "scrollIntoView"], "description": "Action kind"},
        "ref": {"type": "string", "description": "Element ref (e1, e2...)"},
        "selector": {"type": "string", "description": "CSS selector (alternative to ref)"},
        "text": {"type": "string", "description": "Text for 'type' kind"},
        "key": {"type": "string", "description": "Key name for 'press' kind (Enter, Tab, Escape...)"},
        "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Direction for 'scroll' kind"},
        "amount": {"type": "integer", "description": "Pixels to scroll (default: 500)"},
        "doubleClick": {"type": "boolean"},
        "submit": {"type": "boolean", "description": "For 'type': press Enter after typing"},
        "userId": {"type": "string"},
    },
    "required": ["tabId", "kind"],
})

# Tool: youtube_transcript
_t("youtube_transcript", "Extract transcript from a YouTube video via yt-dlp.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "YouTube video URL"},
        "languages": {"type": "array", "items": {"type": "string"}, "default": ["en"]},
    },
    "required": ["url"],
})

# Tool: import_cookies
_t("import_cookies", "Import Netscape-format cookie file for authenticated browsing.", {
    "type": "object",
    "properties": {
        "cookiesPath": {"type": "string", "description": "Path to Netscape cookies.txt file"},
        "userId": {"type": "string"},
    },
    "required": ["cookiesPath"],
})

# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
_handlers = {}

def _default_user(params: dict) -> str:
    return params.pop("userId", "camofox-mcp-user")

async def handle_health_check(params: dict) -> dict:
    try:
        async with httpx.AsyncClient(base_url=CAMOFOX_BASE, timeout=5) as client:
            r = await client.get("/health")
            r.raise_for_status()
            return {"status": "ok", **r.json()}
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def handle_create_tab(params: dict) -> dict:
    user_id = _default_user(params)
    payload = {**params, "userId": user_id}
    if "sessionKey" not in payload:
        payload["sessionKey"] = "mcp-session"
    return await api_post("/tabs", json=payload)

async def handle_open_tab(params: dict) -> dict:
    """Create tab and navigate in one request — uses /tabs/open."""
    user_id = _default_user(params)
    payload = {**params, "userId": user_id}
    if "sessionKey" in payload:
        # map sessionKey -> listItemId (server accepts both, /tabs/open uses listItemId)
        payload["listItemId"] = payload.pop("sessionKey")
    return await api_post("/tabs/open", json=payload)

async def handle_navigate(params: dict) -> dict:
    user_id = _default_user(params)
    payload = {k: v for k, v in params.items() if k not in ("tabId",)}
    payload["userId"] = user_id
    return await api_post(f"/tabs/{params['tabId']}/navigate", json=payload)

async def handle_snapshot(params: dict) -> dict:
    user_id = _default_user(params)
    qs = {"userId": user_id}
    if "offset" in params:
        qs["offset"] = params["offset"]
    return await api_get(f"/tabs/{params['tabId']}/snapshot", params=qs)

async def handle_click(params: dict) -> dict:
    user_id = _default_user(params)
    payload = {k: v for k, v in params.items() if k not in ("tabId",)}
    payload["userId"] = user_id
    return await api_post(f"/tabs/{params['tabId']}/click", json=payload)

async def handle_type_text(params: dict) -> dict:
    user_id = _default_user(params)
    payload = {k: v for k, v in params.items() if k not in ("tabId",)}
    payload["userId"] = user_id
    # Map submit->submit (same key, just ensuring it's passed)
    return await api_post(f"/tabs/{params['tabId']}/type", json=payload)

async def handle_scroll(params: dict) -> dict:
    user_id = _default_user(params)
    payload = {k: v for k, v in params.items() if k not in ("tabId",)}
    payload["userId"] = user_id
    return await api_post(f"/tabs/{params['tabId']}/scroll", json=payload)

async def handle_screenshot(params: dict) -> dict:
    user_id = _default_user(params)
    qs = {"userId": user_id}
    if params.get("fullPage"):
        qs["fullPage"] = "true"
    async with httpx.AsyncClient(base_url=CAMOFOX_BASE, timeout=30) as client:
        r = await client.get(f"/tabs/{params['tabId']}/screenshot", params=qs)
        r.raise_for_status()
        import base64
        data = base64.b64encode(r.content).decode()
        return {"status": "ok", "data": data, "mimeType": "image/png"}

async def handle_links(params: dict) -> dict:
    user_id = _default_user(params)
    qs = {"userId": user_id}
    for k in ("limit", "offset"):
        if k in params:
            qs[k] = str(params[k])
    return await api_get(f"/tabs/{params['tabId']}/links", params=qs)

async def handle_images(params: dict) -> dict:
    user_id = _default_user(params)
    qs = {"userId": user_id}
    for k in ("includeData", "limit", "maxBytes"):
        if k in params:
            qs[k] = str(params[k])
    return await api_get(f"/tabs/{params['tabId']}/images", params=qs)

async def handle_downloads(params: dict) -> dict:
    user_id = _default_user(params)
    qs = {"userId": user_id}
    for k in ("includeData", "consume", "maxBytes"):
        if k in params:
            qs[k] = str(params[k])
    return await api_get(f"/tabs/{params['tabId']}/downloads", params=qs)

async def handle_evaluate(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_post(f"/tabs/{params['tabId']}/evaluate",
                          json={"userId": user_id, "expression": params["expression"]})

async def handle_wait(params: dict) -> dict:
    user_id = _default_user(params)
    payload = {"userId": user_id}
    for k in ("selector", "timeout"):
        if k in params:
            payload[k] = params[k]
    return await api_post(f"/tabs/{params['tabId']}/wait", json=payload)

async def handle_press(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_post(f"/tabs/{params['tabId']}/press",
                          json={"userId": user_id, "key": params["key"]})

async def handle_back(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_post(f"/tabs/{params['tabId']}/back", json={"userId": user_id})

async def handle_forward(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_post(f"/tabs/{params['tabId']}/forward", json={"userId": user_id})

async def handle_refresh(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_post(f"/tabs/{params['tabId']}/refresh", json={"userId": user_id})

async def handle_stats(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_get(f"/tabs/{params['tabId']}/stats", params={"userId": user_id})

async def handle_list_tabs(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_get("/tabs", params={"userId": user_id})

async def handle_close_tab(params: dict) -> dict:
    user_id = _default_user(params)
    return await api_delete(f"/tabs/{params['tabId']}", json={"userId": user_id})

async def handle_close_session(params: dict) -> dict:
    return await api_delete(f"/sessions/{params['userId']}")

async def handle_act(params: dict) -> dict:
    """Unified action dispatcher via /act endpoint. Auto-refreshes stale refs."""
    user_id = _default_user(params)
    kind = params.get("kind")
    # Build the act payload
    act_params = {}
    for k in ("ref", "selector", "text", "key", "direction", "amount", "doubleClick", "submit"):
        if k in params and params[k] is not None:
            act_params[k] = params[k]

    payload = {
        "userId": user_id,
        "kind": kind,
        "targetId": params["tabId"],
        **act_params,
    }
    return await api_post("/act", json=payload)

async def handle_youtube_transcript(params: dict) -> dict:
    payload = {"url": params["url"]}
    if "languages" in params:
        payload["languages"] = params["languages"]
    return await api_post("/youtube/transcript", json=payload, timeout=60)

async def handle_import_cookies(params: dict) -> dict:
    user_id = params.get("userId", "camofox-mcp-user")
    cookies_path = params["cookiesPath"]

    # Read and parse the cookie file
    from pathlib import Path
    cookies_file = Path(cookies_path).expanduser()
    if not cookies_file.exists():
        return {"status": "error", "error": f"Cookie file not found: {cookies_path}"}

    # Parse Netscape cookies format
    cookies = []
    try:
        content = cookies_file.read_text()
    except Exception as e:
        return {"status": "error", "error": f"Failed to read cookie file: {e}"}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        cookies.append({
            "name": fields[5],
            "value": fields[6],
            "domain": fields[0],
            "path": fields[2] if fields[2] else "/",
            "secure": fields[3] == "TRUE",
            "expires": float(fields[4]) if fields[4] != "-1" else -1,
            "httpOnly": False,
        })

    headers = auth_headers()
    async with httpx.AsyncClient(base_url=CAMOFOX_BASE, timeout=30) as client:
        r = await client.post(f"/sessions/{user_id}/cookies",
                              json={"cookies": cookies},
                              headers=headers)
        r.raise_for_status()
        return r.json()

# Map tool names to handlers
_handlers = {
    "health_check": handle_health_check,
    "create_tab": handle_create_tab,
    "open_tab": handle_open_tab,
    "navigate": handle_navigate,
    "snapshot": handle_snapshot,
    "click": handle_click,
    "type_text": handle_type_text,
    "scroll": handle_scroll,
    "screenshot": handle_screenshot,
    "links": handle_links,
    "images": handle_images,
    "downloads": handle_downloads,
    "evaluate": handle_evaluate,
    "wait": handle_wait,
    "press": handle_press,
    "back": handle_back,
    "forward": handle_forward,
    "refresh": handle_refresh,
    "stats": handle_stats,
    "list_tabs": handle_list_tabs,
    "close_tab": handle_close_tab,
    "close_session": handle_close_session,
    "act": handle_act,
    "youtube_transcript": handle_youtube_transcript,
    "import_cookies": handle_import_cookies,
}

# ---------------------------------------------------------------------------
# MCP protocol (JSON-RPC over stdio)
# ---------------------------------------------------------------------------
async def main():
    """MCP stdio protocol loop."""
    running = ensure_camofox_server()
    logger.info("camofox-mcp initialized — server available: %s", running)
    logger.info("camofox-mcp listening on stdio — base=%s", CAMOFOX_BASE)

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            msg = json.loads(line)

            method = msg.get("method", "")
            msg_id = msg.get("id")

            # Respond to handshake
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "camofox-mcp",
                        "version": "1.0.0",
                    },
                }
                await _send({"jsonrpc": "2.0", "id": msg_id, "result": result})
                continue

            if method == "tools/list":
                result = {"tools": TOOLS}
                await _send({"jsonrpc": "2.0", "id": msg_id, "result": result})
                continue

            if method == "tools/call":
                name = msg["params"]["name"]
                args = msg["params"].get("arguments") or {}

                if name not in _handlers:
                    await _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32601, "message": f"Unknown tool: {name}"},
                    })
                    continue

                try:
                    result = await _handlers[name](args)
                    # MCP format: result must be a list of content objects
                    if isinstance(result, dict):
                        # screenshot returns base64 image directly
                        if name == "screenshot":
                            content = [{"type": "resource", "mimeType": result.get("mimeType", "image/png"),
                                        "data": result.get("data", ""),"text": ""}]
                        else:
                            content = [{"type": "text", "text": json.dumps(result)}]
                    else:
                        content = [{"type": "text", "text": str(result)}]
                    await _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"content": content},
                    })
                except httpx.HTTPStatusError as e:
                    await _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32603, "message": f"HTTP {e.response.status_code}: {e.response.text}"},
                    })
                except Exception as e:
                    logger.exception("tool %s failed", name)
                    await _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32603, "message": str(e)},
                    })
                continue

            if method == "notifications/initialized":
                # Client ready signal — nothing to do
                continue

            # Unhandled — acknowledge but ignore
            if method.startswith("notifications/"):
                continue

        except json.JSONDecodeError:
            continue
        except Exception:
            logger.exception("error in main loop")
            break

async def _send(msg: dict):
    line = json.dumps(msg)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
