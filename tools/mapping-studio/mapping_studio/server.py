"""The local web app: a JSON API over a mapping session, plus the static UI.

Stdlib only, on purpose. This gets run on a Raspberry Pi wedged inside a mixer,
over SSH, at one in the morning, and "first pip install a web framework" is not
an acceptable first step. `http.server` is enough for one operator on one
machine, which is the entire audience.

The UI polls rather than holding a socket open. Polling is the right trade here:
the interesting events are human-paced (press a button, click a region), a poll
loop survives the bridge restarting underneath it, and it keeps the client a
single static file with no build step.

SPDX-License-Identifier: MIT
"""

import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import colour, export_mixxx, midi
from .profile import Profile, ProfileError

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class Studio:
    """Everything one running instance owns, behind one lock."""

    def __init__(self, profile, profile_path, session, backdrop=None):
        self.profile = profile
        self.profile_path = profile_path
        self.session = session
        self.backdrop = backdrop
        self.lock = threading.RLock()
        self.dirty = False
        self.mtime = self._mtime()

    def _mtime(self):
        try:
            return os.path.getmtime(self.profile_path)
        except OSError:
            return None

    def save(self, force=False):
        """Write the profile, refusing to clobber an edit made underneath us.

        A studio holds the whole profile in memory, so anything written to the
        file while it runs is invisible to it and disappears at the next save.
        That is not hypothetical: a block added to the file by hand was wiped by
        the next click of Save, silently.
        """
        with self.lock:
            now = self._mtime()
            if not force and self.mtime and now and now > self.mtime + 0.5:
                raise ProfileError(
                    f"{self.profile_path} changed on disk since this studio "
                    f"read it, so saving would discard that edit. Reload to "
                    f"take the file's version, or save with force to keep this "
                    f"one.")
            self.profile.save(self.profile_path)
            self.mtime = self._mtime()
            self.dirty = False
        return self.profile_path

    def reload(self):
        """Re-read the profile from disk, discarding unsaved changes."""
        with self.lock:
            self.profile = Profile.load(self.profile_path)
            self.session.profile = self.profile
            self.mtime = self._mtime()
            self.dirty = False
        return self.profile


class Handler(BaseHTTPRequestHandler):
    studio = None
    server_version = "mapping-studio"

    # Quiet: one line per request drowns the console during a poll loop.
    def log_message(self, fmt, *args):
        if self.path.startswith("/api/state") or self.path.startswith("/api/monitor"):
            return
        super().log_message(fmt, *args)

    # ------------------------------------------------------------- helpers

    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(WEB) or not os.path.isfile(full):
            # The backdrop is the one file allowed from outside the web root,
            # because it is the operator's own local image.
            bd = self.studio.backdrop
            if bd and rel == "backdrop":
                full = bd
            else:
                self.send_error(404)
                return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", _TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ----------------------------------------------------------------- GET

    def do_GET(self):
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self._static(u.path)
        try:
            return self._api_get(u.path, parse_qs(u.query))
        except Exception as exc:                      # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": str(exc)}, 500)

    def _api_get(self, path, q):
        s = self.studio
        with s.lock:
            if path == "/api/state":
                st = s.session.state()
                st["dirty"] = s.dirty
                st["profile_path"] = s.profile_path
                return self._json(st)
            if path == "/api/profile":
                return self._json({
                    "profile": s.profile.data,
                    "backdrop": bool(s.backdrop),
                    "dirty": s.dirty,
                })
            if path == "/api/monitor":
                s.session.pump()
                n = int((q.get("limit") or ["50"])[0])
                return self._json({"events": s.session.monitor(n)})
            if path == "/api/ports":
                return self._json({"ports": midi.list_ports()})
            if path == "/api/palette":
                led = s.profile.data.get("led") or {}
                named = {}
                for n, (r, g, b) in colour.NAMED.items():
                    named[n] = {
                        "hex": colour.hex_of(r, g, b),
                        "bright": colour.named(n, bright=True, led=led),
                        "dim": colour.named(n, bright=False, led=led),
                    }
                return self._json({
                    "spec": colour.spec_from(led),
                    "describe": colour.describe(led),
                    "named": named,
                    "colours": colour.palette(led),
                })
            if path == "/api/export":
                layer = (q.get("layer") or [s.session.layer])[0]
                xml, js, fname = export_mixxx.export(s.profile, layer=layer)
                return self._json({"xml": xml, "script": js, "script_file": fname})
        self.send_error(404)

    # ---------------------------------------------------------------- POST

    def do_POST(self):
        u = urlparse(self.path)
        try:
            return self._api_post(u.path, self._body())
        except ProfileError as exc:
            return self._json({"error": str(exc)}, 400)
        except KeyError as exc:
            return self._json({"error": f"not found: {exc}"}, 404)
        except Exception as exc:                      # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": str(exc)}, 500)

    def _api_post(self, path, body):
        s = self.studio
        with s.lock:
            sess = s.session

            # -- profile editing ---------------------------------------
            if path == "/api/control/add":
                c = s.profile.add_control(body)
                s.dirty = True
                return self._json({"control": c})
            if path == "/api/control/update":
                c = s.profile.update_control(body["id"], body.get("patch") or {})
                s.dirty = True
                return self._json({"control": c})
            if path == "/api/control/rename":
                c = s.profile.rename_control(body["id"], body["new_id"])
                s.dirty = True
                return self._json({"control": c})
            if path == "/api/control/delete":
                ok = s.profile.remove_control(body["id"])
                s.dirty = True
                return self._json({"deleted": ok})
            if path == "/api/binding/clear":
                # Drop one captured binding without touching the region or its
                # Mixxx target -- the fix for an LED recorded on the wrong
                # control, after the probe has moved on.
                s.profile.set_binding(body["id"], body.get("layer") or sess.layer,
                                      body.get("direction", "output"), None)
                s.dirty = True
                return self._json({"control": s.profile.get(body["id"])})
            if path == "/api/control/target":
                c = s.profile.set_target(body["id"],
                                         body.get("layer") or sess.layer,
                                         body.get("target"))
                s.dirty = True
                return self._json({"control": c})

            # -- layers -------------------------------------------------
            if path == "/api/layer":
                name = body.get("layer") or "base"
                if name not in s.profile.layers:
                    s.profile.layers.append(name)
                    s.dirty = True
                sess.layer = name
                return self._json({"layer": name, "layers": s.profile.layers})

            # -- learn --------------------------------------------------
            if path == "/api/learn/start":
                return self._json(sess.start_learn(body["control_id"],
                                                   body.get("layer")))
            if path == "/api/learn/finish":
                res = sess.finish_learn(commit=body.get("commit", True))
                s.dirty = True
                return self._json(res.to_dict() if res else {"error": "not learning"})
            if path == "/api/learn/cancel":
                sess.cancel_learn()
                return self._json({"ok": True})
            if path == "/api/led/local":
                sess.mark_local_led(body["control_id"], body.get("layer"))
                s.dirty = True
                return self._json({"ok": True})
            if path == "/api/silent":
                sess.mark_silent(body["control_id"], body.get("layer"))
                s.dirty = True
                return self._json({"ok": True})

            # -- probe --------------------------------------------------
            if path == "/api/probe/start":
                chans = body.get("channels")
                if not chans:
                    chans = [int(body.get("channel", 1))]
                elif chans == "seen":
                    chans = [d["channel"] for d in sess.seen_summary()] or [1]
                return self._json(sess.start_probe(
                    lo=int(body.get("lo", 0)), hi=int(body.get("hi", 127)),
                    channels=chans,
                    strategy=body.get("strategy", "smart"),
                    hold_ms=int(body.get("hold_ms", 900))))
            if path == "/api/probe/answer":
                s.dirty = True
                return self._json(sess.probe_answer(body.get("control_id")))
            if path == "/api/probe/undo":
                s.dirty = True
                return self._json(sess.probe_undo())
            if path == "/api/probe/skip":
                return self._json(sess.probe_next())
            if path == "/api/probe/stop":
                sess.stop_probe()
                return self._json({"ok": True})
            if path == "/api/colour":
                r, g, b = (float(body.get(k, 0)) for k in ("r", "g", "b"))
                bright = bool(body.get("bright", True))
                if body.get("name"):
                    r, g, b = colour.NAMED[str(body["name"]).lower()]
                if body.get("all_kinds"):
                    n = sess.light_all(r, g, b, bright=bright,
                                       kinds=tuple(body["all_kinds"]))
                    return self._json({"lit": n})
                ok = sess.light(body["control_id"], r, g, b, bright=bright,
                                remember=bool(body.get("remember")))
                if body.get("remember"):
                    s.dirty = True
                return self._json({"ok": ok})
            if path == "/api/blink":
                return self._json({"ok": sess.blink(body["control_id"])})
            if path == "/api/send":
                ok = sess.backend.send(body.get("status", "note_on"),
                                       int(body.get("channel", 1)),
                                       int(body["number"]),
                                       int(body.get("value", 127)))
                return self._json({"ok": ok})

            # -- offline helper ----------------------------------------
            if path == "/api/inject":
                if not hasattr(sess.backend, "inject"):
                    return self._json({"error": "backend is not offline"}, 400)
                sess.backend.inject(body.get("status", "cc"),
                                    int(body.get("channel", 1)),
                                    int(body.get("number", 0)),
                                    int(body.get("value", 0)))
                return self._json({"ok": True})

            # -- persistence -------------------------------------------
            if path == "/api/save":
                return self._json({"saved": s.save(force=bool(body.get("force")))})
            if path == "/api/reload":
                s.reload()
                return self._json({"reloaded": s.profile_path,
                                   "controls": len(s.profile.controls)})
            if path == "/api/export/write":
                layer = body.get("layer") or sess.layer
                outdir = body.get("dir") or os.path.dirname(s.profile_path) or "."
                xml, js, fname = export_mixxx.export(s.profile, layer=layer)
                base = (s.profile.data.get("name") or "mapping").replace(" ", "-")
                xml_path = os.path.join(outdir, f"{base}.midi.xml")
                js_path = os.path.join(outdir, fname)
                with open(xml_path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(xml)
                written = [xml_path]
                if not os.path.exists(js_path):
                    with open(js_path, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write(js)
                    written.append(js_path)
                else:
                    with open(js_path + ".new", "w", encoding="utf-8",
                              newline="\n") as fh:
                        fh.write(js)
                    written.append(js_path + ".new")
                return self._json({"written": written})

        self.send_error(404)


def serve(studio, host="127.0.0.1", port=8733):
    Handler.studio = studio
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd


def load_studio(profile_path, backend_spec="auto", port_hint=None,
                rawmidi=None, sender="aplaymidi", backdrop=None, layer="base"):
    from .session import MappingSession
    prof = Profile.load(profile_path)
    backend = midi.open_backend(backend_spec, port=port_hint, rawmidi=rawmidi,
                                sender=sender)
    backend.start()
    sess = MappingSession(prof, backend, layer=layer)
    return Studio(prof, profile_path, sess, backdrop=backdrop)
