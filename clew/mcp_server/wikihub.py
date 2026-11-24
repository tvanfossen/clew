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

LIVE (round 3, P4c-2a): `/events` streams `rebuilt` (a built wiki was rebuilt after its index
refreshed) and `focus` (the agent's dossier reply named a symbol) to every open page, through a
small script the hub injects into the pages it serves — the static site itself stays
server-free. `/api/<slug>/dossier` and `/api/<slug>/search` answer through `clew.query.export`,
the engine the tools use.

@brief Serve the wiki of every indexed repository from the MCP process.
@version 2
"""

from __future__ import annotations

import html
import json
import logging
import mimetypes
import os
import queue
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
## The switch that lets the hub RUN a test (it executes the repository's code).
RUN_ENV = "CLEW_WIKI_RUN"
## The file under the state root naming the running hub's URL (for `clew wiki open`).
WIKI_RECORD = "wiki.json"
## Seconds a wiki build may take before it is abandoned.
_BUILD_TIMEOUT = 900
## Largest comment request body read, in bytes (2.1): well above the store's own field limits,
## so the store's refusal names the field; anything larger is refused unread.
_COMMENT_MAX_BYTES = 64 * 1024

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


## @brief The live layer's methods, mixed into the hub (round 3, P4c-2a).
## @version 1
class _Live:
    """@brief Events, refresh-driven rebuilds and agent links. @version 1"""

    _subscribers: list[queue.Queue[dict | None]]
    port: int
    host: str

    ## @brief Send an event to every open page.
    ## @param event The event.
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-WIKI-033
    def publish(self, event: dict) -> None:
        """@brief Broadcast. @return None."""
        for subscriber in list(self._subscribers):
            subscriber.put(event)

    ## @brief Subscribe to events.
    ## @return A queue the events arrive on (None ends the stream).
    ## @version 1
    ## @utility
    def subscribe(self) -> queue.Queue[dict | None]:
        """@brief Subscribe. @return Queue."""
        subscriber: queue.Queue[dict | None] = queue.Queue()
        self._subscribers.append(subscriber)
        return subscriber

    ## @brief Stop sending to a subscriber.
    ## @param subscriber Its queue.
    ## @return None.
    ## @version 1
    ## @utility
    def unsubscribe(self, subscriber: queue.Queue[dict | None]) -> None:
        """@brief Unsubscribe. @return None."""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    ## @brief Rebuild the built wikis of targets the refresh loop just refreshed.
    ## @param slugs The refreshed targets.
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-WIKI-033
    def refreshed(self, slugs: list[str]) -> None:
        """A WIKI NOBODY HAS OPENED IS NOT BUILT on a refresh: only one already built is kept
        current, and its open pages are told when the new one is ready.

        @brief Rebuild after a refresh.
        @return None.
        """
        for slug in slugs:
            target = self.find(slug)  # type: ignore[attr-defined]
            if target is None or not Path(target.repo_path).is_dir():
                continue
            if (self.site_dir(target) / "index.html").is_file():  # type: ignore[attr-defined]
                self.request_build(target)  # type: ignore[attr-defined]

    ## @brief The hub URL of a function's symbol section, announcing it to open pages.
    ## @param repo_path The repository the reply answered from.
    ## @param name The function.
    ## @param rel Its file.
    ## @return The URL (no token), or None when the repository is not registered.
    ## @version 1
    ## @req REQ-DDB-WIKI-033
    def link(self, repo_path: str, name: str, rel: str) -> str | None:
        """NO TOKEN IN THE URL: it lands in the model's context and in transcripts; the browser
        that opened the hub holds the session cookie.

        @brief Link a symbol.
        @return URL or None.
        """
        from ..wiki.symbols import symbol_href

        target = next(
            (
                t
                for t in TargetRegistry(self.home).targets()  # type: ignore[attr-defined]
                if t.repo_path == str(repo_path) and t.name is None
            ),
            None,
        )
        if target is None:
            return None
        url = f"http://{self.host}:{self.port}/r/{target.slug}/{symbol_href(name, rel)}"
        self.publish({"type": "focus", "slug": target.slug, "url": url})
        return url


## @brief The hub: an HTTP server on a daemon thread, building wikis on demand.
## @version 1
class WikiHub(_Live):
    """@brief Hub. @version 1"""

    ## @brief Prepare the hub (nothing listens until `start`).
    ## @param home The state root (the registry and every target's wiki live under it).
    ## @param builder Builds one target's site; a subprocess build by default.
    ## v2: event subscribers (P4c-2a).
    ## v3: opt-in channel push of wiki comments (2.1, owner Q/A 2026-11-24)
    ## @version 3
    ## @utility
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
        self._subscribers: list[queue.Queue[dict | None]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        ## 2.1: called with (slug, comment) for a repository whose comments go to the channel.
        self.on_comment: Callable[[str, dict], Any] | None = None

    ## @brief The hub's entry URL, token included.
    ## @return The URL.
    ## @version 1
    ## @utility
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

    ## @brief Stop listening, ending every open event stream.
    ## @return None.
    ## v2: event streams end with the hub (P4c-2a).
    ## @version 2
    ## @req REQ-DDB-WIKI-032
    def stop(self) -> None:
        """@brief Stop. @return None."""
        for subscriber in list(self._subscribers):
            subscriber.put(None)
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        logger.info("clew wiki hub stopped")

    ## @brief Every registered target with its wiki's state.
    ## @return (target, state) pairs.
    ## @version 1
    ## @utility
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
    ## v2: through `wiki_site_dir`, shared with the MCP resources.
    ## @version 2
    ## @utility
    def site_dir(self, target: Target) -> Path:
        """@brief Site directory. @return Path."""
        return wiki_site_dir(target)

    ## @brief "built" when the site exists on disk, else "not built".
    ## @param target The target.
    ## @return The state.
    ## @version 1
    ## @utility
    def _on_disk(self, target: Target) -> str:
        """@brief On-disk state. @return State."""
        return "built" if (self.site_dir(target) / "index.html").is_file() else "not built"

    ## @brief The target with a slug, or None.
    ## @param slug The slug.
    ## @return The target.
    ## @version 1
    ## @utility
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
    ## v2: a finished build is announced to open pages (P4c-2a).
    ## @version 2
    ## @utility
    def _build(self, target: Target) -> None:
        """A FAILED BUILD IS A STATE with its reason, never a crash of the hub.

        @brief Build.
        @return None.
        """
        try:
            self.builder(target, self.site_dir(target).parent)
            outcome = "built"
            self.errors.pop(target.slug, None)
            self.publish({"type": "rebuilt", "slug": target.slug})
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
    ## v2: `/api/`, `/events`, `/live.js` (P4c-2a).
    ## v3: wiki comments (2.1, owner Q/A 2026-11-24)
    ## @version 3
    ## @utility
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
        elif path.startswith("/api/"):
            self._api(path[5:], parse_qs(parts.query))
        elif path == "/events":
            self._events()
        elif path == "/live.js":
            self._send(200, _LIVE_JS.encode("utf-8"), "text/javascript")
        elif path == "/comment.js":
            self._send(200, _COMMENT_JS.encode("utf-8"), "text/javascript")
        else:
            self._send(404, "<p>Not found.</p>")

    ## @brief Accept a comment from a served page (2.1).
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-WIKI-054
    def do_POST(self) -> None:  # noqa: N802 — the http.server spelling
        """THE SAME DOOR AS EVERY PAGE, plus what a write needs: the session cookie (a POST never
        carries `?t=`), JSON only — a cross-site form cannot send it without a preflight the hub
        never answers — the hub's own origin when the browser sends one, and a size cap read from
        the header before any byte of the body. 2.1, owner Q/A 2026-11-24.

        @brief POST.
        @return None.
        """
        refusal = self._post_refusal()
        if refusal is not None:
            self._json(refusal[0], {"error": refusal[1]})
            return
        slug = unquote(urlsplit(self.path).path)[len("/api/") : -len("/comment")]
        self._comment(slug)

    ## @brief Why a POST is refused, or None when it may be read.
    ## @return (status, reason), or None.
    ## @version 1
    ## @utility
    def _post_refusal(self) -> tuple[int, str] | None:
        """@brief POST checks. @return Refusal or None."""
        path = unquote(urlsplit(self.path).path)
        origin = self.headers.get("Origin")
        checks = (
            (
                not secrets.compare_digest(self._cookie(), self.owner.token),
                403,
                "needs the session",
            ),
            (origin is not None and origin != _own_origin(self.owner), 403, "foreign origin"),
            (not (path.startswith("/api/") and path.endswith("/comment")), 404, "not found"),
            (
                not (self.headers.get("Content-Type") or "").startswith("application/json"),
                415,
                "send JSON",
            ),
            (_length(self.headers) > _COMMENT_MAX_BYTES, 413, f"over {_COMMENT_MAX_BYTES} bytes"),
        )
        return next(((code, why) for failed, code, why in checks if failed), None)

    ## @brief Store one comment for a target.
    ## @param slug The target.
    ## @return None.
    ## v2: opt-in channel push of wiki comments (2.1, owner Q/A 2026-11-24)
    ## @version 2
    ## @utility
    def _comment(self, slug: str) -> None:
        """A STORE REFUSAL (empty, a field over its limit) is a 400 carrying its reason, so the page
        can show the person why.

        @brief Comment.
        @return None.
        """
        from .comments import CommentStore

        target = self.owner.find(slug)
        if target is None or not Path(target.repo_path).is_dir():
            self._json(404, {"error": f"no reachable repository {slug!r}"})
            return
        routes = _comment_routes(target.repo_path)
        try:
            fields = _comment_fields(self.rfile.read(_length(self.headers)))
            store = CommentStore.for_repo(self.owner.home, target.repo_path, "hook" in routes)
            stored = store.add(**fields)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        logger.info("wiki comment %s stored for %s (%s)", stored["id"], target.slug, stored["page"])
        if "channel" in routes and self.owner.on_comment is not None:
            self.owner.on_comment(target.slug, stored)
        self._json(201, {"id": stored["id"], "status": stored["status"]})

    ## @brief The session cookie's value, or "".
    ## @return The value.
    ## @version 1
    ## @utility
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
    ## v2: HTML pages carry the live script (P4c-2a).
    ## @version 2
    ## @utility
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
        data = wanted.read_bytes()
        if kind == "text/html":
            data = _with_live_script(data)
        self._send(200, data, kind, set_cookie)

    ## @brief Answer a JSON API call through the same engine the tools use.
    ## @param rest `<slug>/<verb>`.
    ## @param query The query parameters.
    ## @return None.
    ## v2: `trace` — a traced test run with its overlay, opt-in (round 3, P4b).
    ## @version 2
    ## @utility
    def _api(self, rest: str, query: dict[str, list[str]]) -> None:
        """`dossier?subject=&qualified=`, `search?text=&corpus=`, and `trace?test=<node id>` —
        which RUNS the test, so it is refused (403) unless `CLEW_WIKI_RUN=1`. A missing argument
        is a 400, an unknown target a 404, a refused call or a failed run a 400 with its reason.

        @brief API.
        @return None.
        """
        from ..query.export import export_dossier, export_search

        slug, _, verb = rest.partition("/")
        target = self.owner.find(slug)
        arg = {k: v[0] for k, v in query.items() if v}
        if target is None or not Path(target.db_path).is_file():
            self._json(404, {"error": f"no built index for {slug!r}"})
            return
        try:
            if verb == "dossier" and arg.get("subject"):
                reply = export_dossier(
                    target.db_path,
                    arg["subject"],
                    qualified=arg.get("qualified"),
                    repo_root=target.repo_path,
                )
            elif verb == "search" and "text" in arg:
                reply = export_search(
                    target.db_path, arg["text"], corpus=arg.get("corpus", "symbols")
                )
            elif verb == "trace" and arg.get("test"):
                if os.environ.get(RUN_ENV) != "1":
                    self._json(403, {"error": f"running tests is off: set {RUN_ENV}=1"})
                    return
                reply = _traced(target, arg["test"])
            else:
                self._json(400, {"error": "use dossier?subject=… or search?text=…"})
                return
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, reply)

    ## @brief Send a JSON reply.
    ## @param status HTTP status.
    ## @param payload The body.
    ## @return None.
    ## @version 1
    ## @utility
    def _json(self, status: int, payload: Any) -> None:
        """@brief JSON. @return None."""
        self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json")

    ## @brief Hold a server-sent event stream open until the client or the hub goes away.
    ## @return None.
    ## @version 1
    ## @utility
    def _events(self) -> None:
        """A COMMENT EVERY 15 S keeps proxies and the browser from closing an idle stream.

        @brief Event stream.
        @return None.
        """
        subscriber = self.owner.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                if event is None:
                    break
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()
        except OSError:
            pass
        finally:
            self.owner.unsubscribe(subscriber)

    ## @brief Start (or report) a build and answer with a page that refreshes until it is done.
    ## @param target The target.
    ## @param set_cookie Whether to set the session cookie.
    ## @return None.
    ## @version 1
    ## @utility
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
    ## @utility
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
    ## @utility
    def log_message(self, fmt: str, *args: Any) -> None:
        """@brief Log. @return None."""
        logger.debug("wiki hub: " + fmt, *args)


## @brief One test of a target, run traced, with its overlay on the expected flow.
## @param target The target.
## @param nodeid The test's node id.
## @return {passed, checkpoints, failure, dropped, overlay}.
## @version 1
## @req REQ-DDB-WIKI-035
def _traced(target: Target, nodeid: str) -> dict[str, Any]:
    """@brief Traced run. @return Result."""
    from ..wiki.command import expected_steps
    from ..wiki.tracerun import overlay, trace_test

    run = trace_test(Path(target.repo_path), nodeid)
    steps = expected_steps(Path(target.db_path), Path(target.repo_path), nodeid)
    out = {k: run[k] for k in ("passed", "checkpoints", "failure", "dropped")}
    out["overlay"] = overlay(steps, run["otlp"])
    return out


## @brief A page with the live script added before its closing body tag.
## @param data The page.
## @return The page.
## v2: wiki comments (2.1, owner Q/A 2026-11-24)
## @version 2
## @utility
def _with_live_script(data: bytes) -> bytes:
    """2.1: the comment control rides with the live script.

    @brief Inject.
    @return Page.
    """
    tag = b'<script src="/comment.js"></script><script src="/live.js"></script></body>'
    at = data.rfind(b"</body>")
    return data[:at] + tag + data[at + len(b"</body>") :] if at >= 0 else data


## @brief The hub's own origin, as a browser sends it.
## @param hub The hub.
## @return `http://host:port`.
## @version 1
## @utility
def _own_origin(hub: WikiHub) -> str:
    """@brief Origin. @return Text."""
    return f"http://{hub.host}:{hub.port}"


## @brief How a repository's comments reach the agent (`wiki.comments.deliver`).
## @param repo_path The repository.
## @return The routes; `("hook",)` when not declared or unreadable.
## @version 1
## @utility
def _comment_routes(repo_path: str) -> tuple[str, ...]:
    """An unreadable `.clew.yaml` falls back to the hook: the comment is still kept and counted.

    @brief Routes.
    @return Routes.
    """
    from ..wiki.config import load_wiki_config

    try:
        return load_wiki_config(Path(repo_path))[0].comments_deliver
    except Exception as exc:  # noqa: BLE001 — a config error must not lose a comment
        logger.warning(
            "wiki comments for %s: .clew.yaml unreadable (%s); using the hook", repo_path, exc
        )
        return ("hook",)


## @brief A request's declared body length, or 0.
## @param headers The headers.
## @return Bytes.
## @version 1
## @utility
def _length(headers: Any) -> int:
    """@brief Content-Length. @return Int."""
    try:
        return max(0, int(headers.get("Content-Length") or 0))
    except ValueError:
        return 0


## @brief A comment request's four fields, each a string.
## @param raw The request body.
## @return {page, anchor, quote, body}.
## @version 1
## @utility
def _comment_fields(raw: bytes) -> dict[str, str]:
    """@brief Parse. @return Fields; ValueError on anything else."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("send a JSON object")
    fields = {k: data.get(k, "") for k in ("page", "anchor", "quote", "body")}
    if not all(isinstance(v, str) for v in fields.values()):
        raise ValueError("page, anchor, quote and body must be strings")
    return fields


## The live script: rebuilt pages offer a reload; the agent's focus is offered as a link; a test's
## flow offers a traced run drawn over its expected steps (P4b).
_LIVE_JS = """(function () {
  if (!window.EventSource) return;
  var slug = (location.pathname.split('/')[2] || '');
  var bar = document.createElement('div');
  bar.setAttribute('role', 'status');
  bar.style.cssText = 'position:fixed;right:16px;bottom:16px;max-width:420px;padding:10px 14px;' +
    'border-radius:12px;background:#1F3B16;color:#fff;font:14px system-ui;display:none;z-index:99';
  document.body.appendChild(bar);
  function say(html) { bar.innerHTML = html; bar.style.display = 'block'; }
  var block = document.querySelector('.flow-block[data-test-node]');
  if (block) {
    var css = document.createElement('style');
    css.textContent = 'svg.seq g.obs-confirmed .ca,svg.seq g.obs-confirmed line{stroke:#3D6B2E;stroke-width:3}' +
      'svg.seq g.obs-missed{opacity:.25}.trace-panel{margin:10px 0;padding:10px 14px;border-radius:12px;' +
      'border:1px solid #CFC0A0;font:14px system-ui}.trace-panel .bad{color:#A03A26}';
    document.head.appendChild(css);
    var run = document.createElement('button');
    run.type = 'button'; run.textContent = 'Run this test, traced';
    var panel = document.createElement('div'); panel.className = 'trace-panel'; panel.hidden = true;
    block.insertBefore(panel, block.firstChild); block.insertBefore(run, block.firstChild);
    run.onclick = function () {
      run.disabled = true; panel.hidden = false; panel.textContent = 'Running…';
      fetch('/api/' + slug + '/trace?test=' + encodeURIComponent(block.getAttribute('data-test-node')))
        .then(function (r) { return r.json().then(function (j) { return [r.status, j]; }); })
        .then(function (sj) {
          run.disabled = false;
          var j = sj[1];
          if (sj[0] !== 200) { panel.textContent = j.error || 'refused'; return; }
          var steps = block.querySelectorAll('svg.seq g[data-step]');
          (j.overlay.steps || []).forEach(function (s, i) {
            if (steps[i]) steps[i].classList.add(s === 'confirmed' ? 'obs-confirmed' : 'obs-missed');
          });
          panel.textContent = '';
          function line(text, bad) { var d = document.createElement('div'); d.textContent = text; if (bad) d.className = 'bad'; panel.appendChild(d); }
          line(j.passed ? 'Passed.' : 'Failed.', !j.passed);
          (j.checkpoints || []).forEach(function (c) { line('line ' + c.line + ': ' + c.text + ' — ' + c.outcome, c.outcome !== 'passed'); });
          if (j.failure) line('Failure at line ' + j.failure.line + ': ' + j.failure.message, true);
          (j.overlay.discovered || []).forEach(function (d) { line('Discovered (not in the flow): ' + d[0] + ' \u2192 ' + d[1]); });
          var missed = (j.overlay.steps || []).filter(function (s) { return s !== 'confirmed'; }).length;
          if (missed) line(missed + ' predicted step(s) did not run (dimmed).');
        });
    };
  }
  new EventSource('/events').onmessage = function (m) {
    var e = JSON.parse(m.data);
    if (e.slug !== slug) return;
    if (e.type === 'rebuilt') say('This wiki was rebuilt. <a style="color:#fff" href="">Reload</a>');
    if (e.type === 'focus') {
      var a = document.createElement('a');
      a.href = e.url; a.textContent = 'The agent is looking here'; a.style.color = '#fff';
      bar.textContent = ''; bar.appendChild(a); bar.style.display = 'block';
    }
  };
})();
"""


## @brief The hub page: every indexed repository and its wiki's state.
## @param hub The hub.
## @return HTML.
## @version 1
## @utility
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
## @utility
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


## @brief Attach the hub to the server's tools and refresh loop, or detach it.
## @param state The server state (its `tools` and `wiki_hub`).
## @param hub The running hub, or None to detach.
## @return None.
## @version 1
## @req REQ-DDB-WIKI-033
def attach(state: Any, hub: WikiHub | None) -> None:
    """@brief Attach. @return None."""
    if not hasattr(state, "tools"):
        return
    state.wiki_hub = hub
    state.tools.wiki_linker = hub.link if hub is not None else None


## @brief Where a target's built wiki lives: beside its index.
## @param target The target.
## @return The site directory.
## @version 1
## @req REQ-DDB-WIKI-034
def wiki_site_dir(target: Target) -> Path:
    """@brief Site directory. @return Path."""
    return Path(target.db_path).parent / "wiki" / "html"


## @brief One file of a registered target's built wiki, as text — or a sentence saying why not.
## @param registry The target registry.
## @param slug The target's slug.
## @param rel The file, relative to the site.
## @return Its text, or the reason it cannot be served.
## @version 1
## @req REQ-DDB-WIKI-034
def read_wiki_file(registry: TargetRegistry, slug: str, rel: str) -> str:
    """CONFINED to the site, and NEVER EMPTY: an unknown slug, an unbuilt wiki or a missing file
    each says so, because an empty resource reads as "nothing here".

    @brief Read a wiki file.
    @return Text.
    """
    target = next((t for t in registry.targets() if t.slug == slug), None)
    if target is None:
        return f"No indexed repository has the slug {slug!r}; index(action='targets') lists them."
    site = wiki_site_dir(target).resolve()
    wanted = (site / rel).resolve()
    if not wanted.is_relative_to(site):
        return f"{rel!r} is outside the wiki."
    if not (site / "index.html").is_file() and not wanted.is_file():
        return (
            f"The wiki of {slug} is not built. Open it on the wiki hub (CLEW_WIKI=1) or run "
            f"`clew wiki build --repo-root {target.repo_path}`."
        )
    if not wanted.is_file():
        return f"The wiki of {slug} has no {rel!r}."
    return wanted.read_text(encoding="utf-8", errors="replace")


## The comment control (2.1, owner Q/A 2026-11-24): a button on every served page; it sends the
## page, the section it sits in, any selected text and the person's note to `/api/<slug>/comment`.
## Text is written with `textContent` only — nothing a page or a reply holds becomes markup.
_COMMENT_JS = """(function () {
  var slug = (location.pathname.split('/')[2] || '');
  if (!slug) return;
  var page = location.pathname.split('/').slice(3).join('/') || 'index.html';
  var css = document.createElement('style');
  css.textContent = '.clew-c-btn{position:fixed;left:16px;bottom:16px;z-index:98;padding:8px 14px;' +
    'border-radius:999px;border:1px solid #CFC0A0;background:#FBF6EA;font:600 13px system-ui;cursor:pointer}' +
    '.clew-c{position:fixed;left:16px;bottom:60px;z-index:98;width:min(380px,calc(100vw - 32px));padding:12px;' +
    'border-radius:12px;border:1px solid #CFC0A0;background:#FBF6EA;font:14px system-ui;box-shadow:0 6px 24px #0002}' +
    '.clew-c textarea{width:100%;min-height:90px;box-sizing:border-box;font:14px system-ui}' +
    '.clew-c .q{font:12px ui-monospace,monospace;color:#6B5E4D;margin:0 0 6px;max-height:60px;overflow:auto;' +
    'overflow-wrap:anywhere}.clew-c button{margin-top:8px;padding:6px 12px;border-radius:8px;border:1px solid #3D6B2E;' +
    'background:#3D6B2E;color:#fff;font:600 13px system-ui;cursor:pointer}.clew-c button:disabled{opacity:.6}';
  document.head.appendChild(css);
  var btn = document.createElement('button');
  btn.type = 'button'; btn.className = 'clew-c-btn'; btn.textContent = 'Comment';
  var box = document.createElement('div'); box.className = 'clew-c'; box.hidden = true;
  var where = document.createElement('p'); where.className = 'q';
  var text = document.createElement('textarea'); text.setAttribute('aria-label', 'Your comment for the agent');
  var send = document.createElement('button'); send.type = 'button'; send.textContent = 'Send to the agent';
  var said = document.createElement('p'); said.setAttribute('role', 'status');
  box.appendChild(where); box.appendChild(text); box.appendChild(send); box.appendChild(said);
  document.body.appendChild(box); document.body.appendChild(btn);
  var quote = '', anchor = '';
  function section(node) {
    var el = node && (node.nodeType === 1 ? node : node.parentElement);
    while (el && el !== document.body) {
      var h = el.closest ? el.closest('section[id],[id]') : null;
      if (h && h.id) return h.id;
      el = el.parentElement;
    }
    return '';
  }
  btn.onclick = function () {
    var sel = window.getSelection ? String(window.getSelection()) : '';
    quote = sel.slice(0, 1000);
    anchor = section(window.getSelection && window.getSelection().anchorNode) || (location.hash || '').slice(1);
    where.textContent = page + (anchor ? ' #' + anchor : '') + (quote ? ' \u2014 \u201c' + quote + '\u201d' : '');
    said.textContent = '';
    box.hidden = !box.hidden;
    if (!box.hidden) text.focus();
  };
  send.onclick = function () {
    send.disabled = true; said.textContent = 'Sending\u2026';
    fetch('/api/' + slug + '/comment', {
      method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({page: page, anchor: anchor, quote: quote, body: text.value})
    }).then(function (r) { return r.json().then(function (j) { return [r.status, j]; }); })
      .then(function (sj) {
        send.disabled = false;
        if (sj[0] === 201) { said.textContent = 'Sent. The agent is told on its next tool call.'; text.value = ''; }
        else said.textContent = (sj[1] && sj[1].error) || 'Not sent.';
      })
      .catch(function () { send.disabled = false; said.textContent = 'Not sent: the hub did not answer.'; });
  };
})();
"""
