#!/usr/bin/env python3
"""
camofox — Shell CLI for camofox-browser via its REST API.

Usage:
    camofox [options] <command> [args...]

Examples:
    camofox health
    camofox open https://example.com
    camofox snapshot --tab <tabId>
    camofox click e5 --tab <tabId>
    camofox type "hello" e3 --tab <tabId>
    camofox links --tab <tabId>
    camofox screenshot --tab <tabId> --out screenshot.png
    camofox youtube-transcript "https://youtube.com/watch?v=..."
    camofox cookies /tmp/cookies.txt
    camofox act click e5 --tab <tabId>

Environment:
    CAMOFOX_HOST   API host  (default: localhost)
    CAMOFOX_PORT  API port  (default: 9377)
    CAMOFOX_USER  userId for session (default: cli-default)
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("error: httpx required — pip install httpx", file=sys.stderr)
    sys.exit(1)

HOST = os.environ.get("CAMOFOX_HOST", "localhost")
PORT = os.environ.get("CAMOFOX_PORT", "9377")
BASE = f"http://{HOST}:{PORT}"
USER = os.environ.get("CAMOFOX_USER", "cli-default")
TIMEOUT = 30.0

def api_get(path: str, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    r = httpx.get(BASE + path, **kwargs)
    r.raise_for_status()
    return r.json()

def api_post(path: str, json=None, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    r = httpx.post(BASE + path, json=json, **kwargs)
    r.raise_for_status()
    return r.json()

def api_delete(path: str, json=None, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    r = httpx.delete(BASE + path, json=json, **kwargs)
    r.raise_for_status()
    return r.json()

def out(data):
    print(json.dumps(data, indent=2))

def main():
    p = argparse.ArgumentParser(prog="camofox", description="camofox-browser CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # health
    sub.add_parser("health", help="Check server health")

    # open
    do_open = sub.add_parser("open", help="Open URL in new tab")
    do_open.add_argument("url")
    do_open.add_argument("--tab", dest="tab", help="Tab ID (opens new tab if omitted)")

    # create-tab
    do_tab = sub.add_parser("create-tab", help="Create empty tab")
    do_tab.add_argument("--url", default=None)

    # navigate
    do_nav = sub.add_parser("navigate", help="Navigate existing tab")
    do_nav.add_argument("url")
    do_nav.add_argument("--tab", required=True)

    # snapshot
    do_snap = sub.add_parser("snapshot", help="Get page snapshot")
    do_snap.add_argument("--tab", required=True)
    do_snap.add_argument("--offset", type=int, default=None)

    # click
    do_click = sub.add_parser("click", help="Click element")
    do_click.add_argument("target", help="Element ref (e5) or CSS selector")
    do_click.add_argument("--tab", required=True)
    do_click.add_argument("--double", action="store_true")

    # type
    do_type = sub.add_parser("type", help="Type text into element")
    do_type.add_argument("text")
    do_type.add_argument("target", nargs="?", default=None, help="Element ref or selector")
    do_type.add_argument("--tab", required=True)
    do_type.add_argument("--submit", action="store_true")

    # scroll
    do_scroll = sub.add_parser("scroll", help="Scroll page")
    do_scroll.add_argument("--tab", required=True)
    do_scroll.add_argument("--dir", default="down", choices=["up","down","left","right"])
    do_scroll.add_argument("--amount", type=int, default=500)

    # screenshot
    do_shot = sub.add_parser("screenshot", help="Take screenshot")
    do_shot.add_argument("--tab", required=True)
    do_shot.add_argument("--out", default="screenshot.png")
    do_shot.add_argument("--full", action="store_true")

    # links
    do_links = sub.add_parser("links", help="Extract links")
    do_links.add_argument("--tab", required=True)
    do_links.add_argument("--limit", type=int, default=50)
    do_links.add_argument("--offset", type=int, default=0)

    # images
    do_imgs = sub.add_parser("images", help="Extract image metadata")
    do_imgs.add_argument("--tab", required=True)
    do_imgs.add_argument("--limit", type=int, default=8)
    do_imgs.add_argument("--data", action="store_true", help="Include inline data URLs")

    # downloads
    do_dl = sub.add_parser("downloads", help="List downloads")
    do_dl.add_argument("--tab", required=True)
    do_dl.add_argument("--consume", action="store_true")

    # evaluate
    do_eval = sub.add_parser("eval", help="Run JavaScript")
    do_eval.add_argument("expr")
    do_eval.add_argument("--tab", required=True)

    # wait
    do_wait = sub.add_parser("wait", help="Wait for selector")
    do_wait.add_argument("--tab", required=True)
    do_wait.add_argument("--selector")
    do_wait.add_argument("--timeout", type=int, default=15000)

    # press
    do_press = sub.add_parser("press", help="Press keyboard key")
    do_press.add_argument("key")
    do_press.add_argument("--tab", required=True)

    # back / forward / refresh
    for cmd, help_ in [("back","Navigate back"),("forward","Navigate forward"),("refresh","Reload page")]:
        sp = sub.add_parser(cmd, help=help_)
        sp.add_argument("--tab", required=True)

    # stats
    do_stats = sub.add_parser("stats", help="Tab statistics")
    do_stats.add_argument("--tab", required=True)

    # list-tabs
    sub.add_parser("list-tabs", help="List open tabs")

    # close-tab
    do_close = sub.add_parser("close-tab", help="Close a tab")
    do_close.add_argument("--tab", required=True)

    # cookies / import-cookies
    do_cook = sub.add_parser("cookies", help="Import Netscape cookie file")
    do_cook.add_argument("file")

    # youtube-transcript
    do_yt = sub.add_parser("youtube-transcript", help="Get YouTube transcript")
    do_yt.add_argument("url")
    do_yt.add_argument("--lang", default="en", help="Language code (default: en)")

    # act
    do_act = sub.add_parser("act", help="Unified action (click|type|press|scroll)")
    do_act.add_argument("kind", choices=["click","type","press","scroll"])
    do_act.add_argument("--tab", required=True)
    do_act.add_argument("--ref")
    do_act.add_argument("--selector")
    do_act.add_argument("--text")
    do_act.add_argument("--key")
    do_act.add_argument("--dir", dest="direction")
    do_act.add_argument("--amount", type=int)
    do_act.add_argument("--double", dest="doubleClick", action="store_true")
    do_act.add_argument("--submit", action="store_true")

    args = p.parse_args()
    uid = USER

    try:
        if args.cmd == "health":
            out(api_get("/health"))

        elif args.cmd == "open":
            payload = {"url": args.url, "userId": uid}
            out(api_post("/tabs/open", json=payload))

        elif args.cmd == "create-tab":
            payload = {"userId": uid, "sessionKey": "default"}
            if args.url:
                payload["url"] = args.url
            out(api_post("/tabs", json=payload))

        elif args.cmd == "navigate":
            out(api_post(f"/tabs/{args.tab}/navigate", json={"url": args.url, "userId": uid}))

        elif args.cmd == "snapshot":
            qs = {"userId": uid}
            if args.offset:
                qs["offset"] = args.offset
            out(api_get(f"/tabs/{args.tab}/snapshot", params=qs))

        elif args.cmd == "click":
            payload = {"userId": uid}
            t = args.target
            if t and t[0] == "e" and t[1:].isdigit():
                payload["ref"] = t
            else:
                payload["selector"] = t or ""
            if args.double:
                payload["doubleClick"] = True
            out(api_post(f"/tabs/{args.tab}/click", json=payload))

        elif args.cmd == "type":
            payload = {"userId": uid, "text": args.text}
            if args.target:
                t = args.target
                if t[0] == "e" and t[1:].isdigit():
                    payload["ref"] = t
                else:
                    payload["selector"] = t
            if args.submit:
                payload["submit"] = True
            out(api_post(f"/tabs/{args.tab}/type", json=payload))

        elif args.cmd == "scroll":
            out(api_post(f"/tabs/{args.tab}/scroll", json={
                "userId": uid, "direction": args.dir, "amount": args.amount
            }))

        elif args.cmd == "screenshot":
            qs = {"userId": uid}
            if args.full:
                qs["fullPage"] = "true"
            r = httpx.get(BASE + f"/tabs/{args.tab}/screenshot", params=qs, timeout=TIMEOUT)
            r.raise_for_status()
            data = base64.b64decode(r.content)
            Path(args.out).write_bytes(data)
            print(f"Saved to {args.out} ({len(data):,} bytes)")

        elif args.cmd == "links":
            out(api_get(f"/tabs/{args.tab}/links", params={
                "userId": uid, "limit": args.limit, "offset": args.offset
            }))

        elif args.cmd == "images":
            qs = {"userId": uid, "limit": args.limit}
            if args.data:
                qs["includeData"] = "true"
            out(api_get(f"/tabs/{args.tab}/images", params=qs))

        elif args.cmd == "downloads":
            qs = {"userId": uid}
            if args.consume:
                qs["consume"] = "true"
            out(api_get(f"/tabs/{args.tab}/downloads", params=qs))

        elif args.cmd == "eval":
            out(api_post(f"/tabs/{args.tab}/evaluate", json={"userId": uid, "expression": args.expr}))

        elif args.cmd == "wait":
            payload = {"userId": uid, "timeout": args.timeout}
            if args.selector:
                payload["selector"] = args.selector
            out(api_post(f"/tabs/{args.tab}/wait", json=payload))

        elif args.cmd == "press":
            out(api_post(f"/tabs/{args.tab}/press", json={"userId": uid, "key": args.key}))

        elif args.cmd == "back":
            out(api_post(f"/tabs/{args.tab}/back", json={"userId": uid}))

        elif args.cmd == "forward":
            out(api_post(f"/tabs/{args.tab}/forward", json={"userId": uid}))

        elif args.cmd == "refresh":
            out(api_post(f"/tabs/{args.tab}/refresh", json={"userId": uid}))

        elif args.cmd == "stats":
            out(api_get(f"/tabs/{args.tab}/stats", params={"userId": uid}))

        elif args.cmd == "list-tabs":
            out(api_get("/tabs", params={"userId": uid}))

        elif args.cmd == "close-tab":
            out(api_delete(f"/tabs/{args.tab}", json={"userId": uid}))

        elif args.cmd == "cookies":
            cookies_file = Path(args.file).expanduser()
            if not cookies_file.exists():
                print(f"error: file not found: {args.file}", file=sys.stderr)
                sys.exit(1)
            cookies = []
            for line in cookies_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) < 7:
                    continue
                cookies.append({
                    "name": fields[5], "value": fields[6],
                    "domain": fields[0],
                    "path": fields[2] if fields[2] else "/",
                    "secure": fields[3] == "TRUE",
                    "expires": float(fields[4]) if fields[4] != "-1" else -1,
                    "httpOnly": False,
                })
            out(api_post(f"/sessions/{uid}/cookies", json={"cookies": cookies}))

        elif args.cmd == "youtube-transcript":
            out(api_post("/youtube/transcript", json={
                "url": args.url, "languages": [args.lang]
            }, timeout=60))

        elif args.cmd == "act":
            payload = {"userId": uid, "kind": args.kind, "targetId": args.tab}
            for k, v in [
                ("ref", args.ref), ("selector", args.selector), ("text", args.text),
                ("key", args.key), ("direction", args.direction), ("amount", args.amount),
                ("doubleClick", getattr(args, "doubleClick", False)),
                ("submit", args.submit),
            ]:
                if v is not None:
                    payload[k] = v
            out(api_post("/act", json=payload))

    except httpx.HTTPStatusError as e:
        print(f"error: HTTP {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
