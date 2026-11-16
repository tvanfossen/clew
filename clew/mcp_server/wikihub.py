# SPDX-License-Identifier: MIT
"""The wiki hub: an opt-in HTTP thread inside the MCP server (round 3, P4c).

Owner 2026-11-16: the wiki is served FROM THE MCP SERVER — not a separate server — and is "a
central spot to explore all clew indexed repos". One process then holds the target registry,
the refresh loop and the indexes, and the agent and the person in the browser see one state.

  * OPT-IN (`CLEW_WIKI=1`): with it unset nothing listens.
  * LOOPBACK ONLY, a port the OS picks, and a PER-SESSION TOKEN on every request — the first
    visit carries it as `?t=`, which sets an HttpOnly, SameSite=Strict cookie; anything else is
    refused. One page lists every repository indexed on this machine, so it is not left open to
    other local users' browsers.
  * `/` lists every registered target with its wiki's state — built, building, not built, failed,
    or UNREACHABLE when its checkout is gone (listed, never dropped).
  * `/r/<slug>/…` serves that target's wiki, BUILT ON DEMAND in a subprocess (Sphinx must never
    block a tool call), one build at a time, cached beside the target's index.
  * STDOUT IS THE JSON-RPC WIRE: request logging goes to the logger, never to stdout.

@brief Serve the wiki of every indexed repository from the MCP process.
@version 1
"""

from __future__ import annotations

import html
import json
import logging
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

from .state import Target, TargetRegistry

logger = logging.getLogger(__name__)

## The environment switch that turns the hub on.
WIKI_ENV = "CLEW_WIKI"
## The file under the state root naming the running hub's URL (for `clew wiki open`).
WIKI_RECORD = "wiki.json"
## Seconds a wiki build may take before it is abandoned.
_BUILD_TIMEOUT = 900

Builder = Callable[[Target, Path], Path]


## @brief Build one target's wiki in a subprocess.
## @param target The target.
## @param out The output directory; the site is `<out>/html`.
## @return The site directory.
## @version 1
## @req REQ-DDB-WIKI-032
def build_in_subprocess(target: Target, out: Path) -> Path:
    """A SUBPROCESS, so Sphinx's imports, memory and time never land on the MCP event loop, and
    its output — which goes to its own pipes — can never reach this process's stdout.

    @brief Build a wiki.
    @return Site directory.
    """
    argv = [
        sys.executable,
        "-m",
        "clew",
        "wiki",
        "build",
        "--index",
        target.db_path,
        "--repo-root",
        target.repo_path,
        "--out",
        str(out),
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=_BUILD_TIMEOUT, check=False)
    if done.returncode != 0:
        raise RuntimeError(
            (done.stderr or done.stdout).strip()[-2000:] or f"exit {done.returncode}"
        )
    return out / "html"


## @brief The hub: an HTTP server on a daemon thread, building wikis on demand.
## @version 1
class WikiHub:
    """@brief Hub. @version 1"""

    ## @brief Prepare the hub (nothing listens until `start`).
    ## @param home The state root (the registry and every target's wiki live under it).
    ## @param builder Builds one target's site; a subprocess build by default.
    ## @version 1
    ## @dg_internal
    def __init__(self, home: Path, builder: Builder | None = None) -> None:
        """@brief Store. @return None."""
        self.home = Path(home)
        self.builder = builder or build_in_subprocess
        self.token = secrets.token_urlsafe(24)
        self.host = "127.0.0.1"
        self.port = 0
        self.state: dict[str, str] = {}
        self.errors: dict[str, str] = {}
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    ## @brief The hub's entry URL, token included.
    ## @return The URL.
    ## @version 1
    ## @dg_internal
    @property
    def url(self) -> str:
        """@brief URL. @return URL."""
        return f"http://{self.host}:{self.port}/?t={self.token}"

    ## @brief Start listening on a daemon thread.
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-WIKI-032
    def start(self) -> None:
        """@brief Start. @return None."""
        hub = self

        class _Handler(_HubHandler):
            owner = hub

        self._server = ThreadingHTTPServer((self.host, 0), _Handler)
        self._server.daemon_threads = True
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="clew-wiki-hub", daemon=True
        )
        self._thread.start()
        logger.info("clew wiki hub listening on %s:%d", self.host, self.port)

    ## @brief Stop listening.
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-WIKI-032
    def stop(self) -> None:
        """@brief Stop. @return None."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        logger.info("clew wiki hub stopped")

    ## @brief Every registered target with its wiki's state.
    ## @return (target, state) pairs.
    ## @version 1
    ## @dg_internal
    def listing(self) -> list[tuple[Target, str]]:
        """UNREACHABLE when the checkout is gone; else building / failed / built / not built.

        @brief List.
        @return Pairs.
        """
        out = []
        for target in TargetRegistry(self.home).targets():
            if not Path(target.repo_path).is_dir():
                out.append((target, "unreachable"))
            else:
                out.append((target, self.state.get(target.slug) or self._on_disk(target)))
        return out

    ## @brief A target's site directory (built or not).
    ## @param target The target.
    ## @return The directory.
    ## @version 1
    ## @dg_internal
    def site_dir(self, target: Target) -> Path:
        """@brief Site directory. @return Path."""
        return Path(target.db_path).parent / "wiki" / "html"

    ## @brief "built" when the site exists on disk, else "not built".
    ## @param target The target.
    ## @return The state.
    ## @version 1
    ## @dg_internal
    def _on_disk(self, target: Target) -> str:
        """@brief On-disk state. @return State."""
        return "built" if (self.site_dir(target) / "index.html").is_file() else "not built"

    ## @brief The target with a slug, or None.
    ## @param slug The slug.
    ## @return The target.
    ## @version 1
    ## @dg_internal
    def find(self, slug: str) -> Target | None:
        """@brief Look up. @return Target."""
        return next((t for t in TargetRegistry(self.home).targets() if t.slug == slug), None)

    ## @brief Start a build for a target unless one is running; one build at a time.
    ## @param target The target.
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-WIKI-032
    def request_build(self, target: Target) -> None:
        """@brief Build on demand. @return None."""
        with self._lock:
            if "building" in self.state.values():
                if self.state.get(target.slug) != "building":
                    self.state.setdefault(target.slug, "queued")
                return
            self.state[target.slug] = "building"
        threading.Thread(target=self._build, args=(target,), daemon=True).start()

    ## @brief Run one build, then the next queued one.
    ## @param target The target.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def _build(self, target: Target) -> None:
        """A FAILED BUILD IS A STATE with its reason, never a crash of the hub.

        @brief Build.
        @return None.
        """
        try:
            self.builder(target, self.site_dir(target).parent)
            outcome = "built"
            self.errors.pop(target.slug, None)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            logger.error("wiki build for %s failed: %s", target.slug, exc)
            self.errors[target.slug] = str(exc)
            outcome = "failed"
        with self._lock:
            self.state[target.slug] = outcome
            queued = next((s for s, v in self.state.items() if v == "queued"), None)
        nxt = self.find(queued) if queued else None
        if nxt is not None:
            with self._lock:
                self.state.pop(nxt.slug, None)
            self.request_build(nxt)


## @brief Request handling: the token, the hub page, and the per-target sites.
## @version 1
class _HubHandler(BaseHTTPRequestHandler):
    """@brief Handler. @version 1"""

    owner: WikiHub
    server_version = "clew-wiki"

    ## @brief Serve a GET.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def do_GET(self) -> None:  # noqa: N802 — the http.server spelling
        """@brief GET. @return None."""
        parts = urlsplit(self.path)
        token = (parse_qs(parts.query).get("t") or [""])[0]
        cookie = self._cookie()
        if not secrets.compare_digest(token or cookie, self.owner.token):
            self._send(403, "<p>This page needs the session's link.</p>")
            return
        path = unquote(parts.path)
        if path in ("", "/"):
            self._send(200, _hub_page(self.owner), set_cookie=bool(token))
        elif path.startswith("/r/"):
            self._site(path[3:], set_cookie=bool(token))
        else:
            self._send(404, "<p>Not found.</p>")

    ## @brief The session cookie's value, or "".
    ## @return The value.
    ## @version 1
    ## @dg_internal
    def _cookie(self) -> str:
        """@brief Cookie. @return Token."""
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "clew_wiki":
                return value
        return ""

    ## @brief Serve a file of a target's site, building it first when needed.
    ## @param rest `<slug>/<path>`.
    ## @param set_cookie Whether to set the session cookie.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def _site(self, rest: str, set_cookie: bool) -> None:
        """CONFINED: the requested file must resolve inside the built site.

        @brief Serve a site file.
        @return None.
        """
        slug, _, inner = rest.partition("/")
        target = self.owner.find(slug)
        if target is None or not Path(target.repo_path).is_dir():
            self._send(404, "<p>No such reachable repository.</p>")
            return
        site = self.owner.site_dir(target)
        wanted = (site / (inner or "index.html")).resolve()
        if not wanted.is_relative_to(site.resolve()):
            self._send(404, "<p>Not found.</p>")
            return
        if not (site / "index.html").is_file():
            self._building(target, set_cookie)
            return
        if not wanted.is_file():
            self._send(404, "<p>Not found.</p>")
            return
        kind = mimetypes.guess_type(wanted.name)[0] or "application/octet-stream"
        self._send(200, wanted.read_bytes(), kind, set_cookie)

    ## @brief Start (or report) a build and answer with a page that refreshes until it is done.
    ## @param target The target.
    ## @param set_cookie Whether to set the session cookie.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def _building(self, target: Target, set_cookie: bool) -> None:
        """@brief Building page. @return None."""
        state = self.owner.state.get(target.slug)
        if state == "failed":
            reason = html.escape(self.owner.errors.get(target.slug, ""))
            self._send(
                500, f"<h1>The wiki build failed</h1><pre>{reason}</pre>", set_cookie=set_cookie
            )
            return
        if state not in ("building", "queued"):
            self.owner.request_build(target)
        body = (
            '<meta http-equiv="refresh" content="3"><h1>Building the wiki of '
            f"{html.escape(target.slug)}…</h1><p>This page reloads until it is ready.</p>"
        )
        self._send(202, body, set_cookie=set_cookie)

    ## @brief Send a reply.
    ## @param status HTTP status.
    ## @param body Bytes, or an HTML fragment.
    ## @param kind Content type.
    ## @param set_cookie Whether to set the session cookie.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def _send(
        self, status: int, body: bytes | str, kind: str = "text/html", set_cookie: bool = False
    ) -> None:
        """@brief Reply. @return None."""
        data = body if isinstance(body, bytes) else _wrap(body).encode("utf-8")
        self.send_response(status)
        self.send_header(
            "Content-Type", f"{kind}; charset=utf-8" if kind.startswith("text/") else kind
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header(
                "Set-Cookie", f"clew_wiki={self.owner.token}; HttpOnly; SameSite=Strict; Path=/"
            )
        self.end_headers()
        self.wfile.write(data)

    ## @brief Request logging through the logger — never stderr's default, never stdout.
    ## @param fmt The format.
    ## @param args Its arguments.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def log_message(self, fmt: str, *args: Any) -> None:
        """@brief Log. @return None."""
        logger.debug("wiki hub: " + fmt, *args)


## @brief The hub page: every indexed repository and its wiki's state.
## @param hub The hub.
## @return HTML.
## @version 1
## @dg_internal
def _hub_page(hub: WikiHub) -> str:
    """@brief Hub page. @return HTML."""
    rows = []
    for target, state in hub.listing():
        name = html.escape(target.slug)
        link = name if state == "unreachable" else f'<a href="/r/{name}/">{name}</a>'
        rows.append(
            f"<tr><td>{link}</td><td><code>{html.escape(target.repo_path)}</code></td>"
            f'<td class="s-{state.replace(" ", "-")}">{state}</td></tr>'
        )
    body = "".join(rows) or '<tr><td colspan="3">No repository is indexed yet.</td></tr>'
    return (
        "<h1>clew — indexed repositories</h1>"
        "<p>Every repository this machine's clew has indexed. Open one to read its wiki; a wiki "
        "is built the first time it is opened.</p>"
        f"<table><thead><tr><th>repository</th><th>path</th><th>wiki</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


## @brief A fragment as a complete small page.
## @param fragment The body.
## @return HTML.
## @version 1
## @dg_internal
def _wrap(fragment: str) -> str:
    """@brief Page. @return HTML."""
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>clew wiki</title><style>'
        "body{font:15px/1.5 system-ui,sans-serif;margin:32px;color:#2A2118;background:#FAF1D9}"
        "table{border-collapse:collapse}td,th{padding:6px 12px;border-bottom:1px solid #CFC0A0;"
        "text-align:left}.s-unreachable,.s-failed{color:#A03A26}.s-built{color:#3D6B2E}"
        f"</style></head><body>{fragment}</body></html>"
    )


## @brief Start the hub when `CLEW_WIKI=1`, recording its URL under the state root.
## @param home The state root.
## @return The running hub, or None when the hub is off.
## @version 1
## @req REQ-DDB-WIKI-032
def start_if_enabled(home: Path) -> WikiHub | None:
    """THE URL IS RECORDED so `clew wiki open` (and the person) can find the running hub; the file
    is CREATED private to the user (0600) — never written and then narrowed — because the URL
    carries the token.

    @brief Maybe start the hub.
    @return Hub or None.
    """
    if os.environ.get(WIKI_ENV) != "1":
        return None
    hub = WikiHub(home)
    hub.start()
    record = Path(home) / WIKI_RECORD
    record.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(json.dumps({"url": hub.url, "pid": os.getpid()}))
    return hub


## @brief Stop the hub and remove its URL record.
## @param hub The hub, or None.
## @param home The state root.
## @return None.
## @version 1
## @req REQ-DDB-WIKI-032
def stop(hub: WikiHub | None, home: Path) -> None:
    """@brief Stop. @return None."""
    if hub is None:
        return
    hub.stop()
    (Path(home) / WIKI_RECORD).unlink(missing_ok=True)
