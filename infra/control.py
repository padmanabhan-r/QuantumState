"""
QuantumState — Local Infrastructure Control Panel
Usage: uv run python infra/control.py
"""

import asyncio
import httpx
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Button, Label, Log
from textual.widget import Widget
from textual import work

# ─── Config ──────────────────────────────────────────────────────────────────

SERVICES = [
    {"name": "payment-service",   "port": 8001},
    {"name": "checkout-service",  "port": 8002},
    {"name": "auth-service",      "port": 8003},
    {"name": "inventory-service", "port": 8004},
]
POLL_SECONDS = 3

# ─── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
Screen {
    background: #0d0d14;
}
Header {
    background: #111117;
    color: #a5b4fc;
    text-style: bold;
}
Footer {
    background: #111117;
    color: #4b5563;
}

/* ── Two column layout ── */
#main {
    layout: horizontal;
    height: 1fr;
}
#left {
    width: 1fr;
    padding: 1 2;
    border-right: solid #1e2040;
}
#right {
    width: 1fr;
    padding: 1 2;
}

/* ── Headings ── */
.h {
    color: #4b5563;
    text-style: bold;
    margin-bottom: 1;
}

/* ── Docker compose buttons ── */
#compose-row {
    height: 5;
    margin-bottom: 2;
    align: left middle;
}

/* ── Service cards ── */
.svc {
    height: 10;
    border: solid #1e2040;
    background: #111117;
    padding: 1 2;
    margin-bottom: 1;
}
.svc.healthy  { border: solid #064e3b; }
.svc.degraded { border: solid #92400e; }
.svc.offline  { border: solid #1f2937; }
.svc-name     { color: #e5e7eb; text-style: bold; }
.svc-status   { color: #374151; }
.svc-status.healthy  { color: #6ee7b7; }
.svc-status.degraded { color: #fb923c; }
.svc-metrics  { color: #6b7280; margin-top: 1; }

/* ── Inject cards ── */
.inject-card {
    height: 10;
    border: solid #1e3554;
    background: #0a1120;
    padding: 1 2;
    margin-bottom: 1;
}
.inject-name { color: #93c5fd; text-style: bold; }
.inject-meta { color: #374151; margin-bottom: 1; }

/* ── Log ── */
#log-wrap {
    border: solid #1e2040;
    background: #080810;
    height: 1fr;
    padding: 0 1;
    margin-top: 1;
}
Log {
    background: #080810;
    color: #6b7280;
}

/* ── Buttons ── */
Button { margin: 0 1 0 0; height: 3; min-width: 14; }

.btn-start   { background: #064e3b; color: #6ee7b7; border: solid #065f46; }
.btn-start:focus { background: #065f46; }
.btn-stop    { background: #1c0a0a; color: #f87171; border: solid #7f1d1d; }
.btn-stop:focus { background: #7f1d1d; }
.btn-misc    { background: #111827; color: #9ca3af; border: solid #374151; }
.btn-misc:focus { background: #374151; }
.btn-inject  { background: #1e3a5f; color: #93c5fd; border: solid #2563eb; }
.btn-inject:focus { background: #2563eb; }
.btn-reset   { background: #111827; color: #6b7280;  border: solid #374151; }
.btn-reset:focus { background: #374151; }
.btn-reset-all { background: #1c0a0a; color: #f87171; border: solid #7f1d1d; width: 1fr; margin-bottom: 1; }
.btn-reset-all:focus { background: #7f1d1d; }
"""

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ─── Service Card ─────────────────────────────────────────────────────────────

class ServiceCard(Widget):
    def __init__(self, svc: dict, **kwargs):
        super().__init__(**kwargs)
        self._svc = svc
        self._last_status: str | None = None

    def compose(self) -> ComposeResult:
        p = self._svc["port"]
        yield Label(self._svc["name"], classes="svc-name")
        yield Label("● connecting", id=f"s{p}-st", classes="svc-status")
        yield Static("", id=f"s{p}-m", classes="svc-metrics")

    def refresh_data(self, d: dict | None):
        p   = self._svc["port"]
        st  = self.query_one(f"#s{p}-st",  Label)
        met = self.query_one(f"#s{p}-m",   Static)
        self.remove_class("healthy", "degraded", "offline")

        if d is None:
            # Do NOT clear _last_status — preserve it so that when the container
            # comes back after a Docker restart we can still detect the degraded→healthy
            # transition in _poll (otherwise prev becomes None and the log never fires).
            self.add_class("offline")
            st.update("● offline")
            st.set_classes("svc-status")
            met.update("")
            return

        self._last_status = d.get("status")
        deg   = d.get("status") == "degraded"
        fault = d.get("fault") or ""
        self.add_class("degraded" if deg else "healthy")
        st.update(f"▲ {fault}" if deg else "● healthy")
        st.set_classes(f"svc-status {'degraded' if deg else 'healthy'}")

        mem = d.get("memory_percent", 0)
        err = d.get("error_rate", 0)
        lat = d.get("latency_ms", 0)
        cpu = d.get("cpu_percent", 0)
        met.update(
            f"mem {mem:.1f}%  cpu {cpu:.1f}%\n"
            f"err {err:.1f}/m  lat {lat:.0f}ms"
        )

# ─── App ─────────────────────────────────────────────────────────────────────

class ControlPanel(App):
    TITLE = "QuantumState · Local Control Panel"
    CSS = CSS
    BINDINGS = [
        Binding("q", "quit",         "Quit"),
        Binding("r", "do_refresh",   "Refresh"),
        Binding("1", "inject_leak",  "Inject leak"),
        Binding("2", "inject_spike", "Inject spike"),
        Binding("0", "reset_all",    "Reset all"),
    ]

    def __init__(self):
        super().__init__()
        self._cards: dict[str, ServiceCard] = {}
        self._http = httpx.AsyncClient(timeout=4.0)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="main"):

            # ── LEFT: docker + services ───────────────────────────────
            with Vertical(id="left"):
                yield Label("── docker compose", classes="h")
                with Horizontal(id="compose-row"):
                    yield Button("▶ Start", id="btn-up",      classes="btn-start")
                    yield Button("■ Stop",  id="btn-down",    classes="btn-stop")
                    yield Button("↺ Restart", id="btn-restart", classes="btn-misc")
                    yield Label("", id="compose-status")

                yield Label("── services", classes="h")
                for svc in SERVICES:
                    card = ServiceCard(svc, classes="svc offline", id=f"card-{svc['port']}")
                    self._cards[svc["name"]] = card
                    yield card

            # ── RIGHT: inject + log ───────────────────────────────────
            with Vertical(id="right"):
                yield Label("── inject anomaly", classes="h")

                with Vertical(classes="inject-card"):
                    yield Label("🧠  Memory Leak", classes="inject-name")
                    yield Label("payment-service · +4 MB/5 s · ~25 min to critical", classes="inject-meta")
                    with Horizontal():
                        yield Button("Inject [1]", id="btn-leak",       classes="btn-inject")
                        yield Button("Reset",      id="btn-reset-leak", classes="btn-reset")

                with Vertical(classes="inject-card"):
                    yield Label("⚡  Error Spike", classes="inject-name")
                    yield Label("auth-service · 18-24 errors/min · 600 s duration", classes="inject-meta")
                    with Horizontal():
                        yield Button("Inject [2]", id="btn-spike",       classes="btn-inject")
                        yield Button("Reset",      id="btn-reset-spike", classes="btn-reset")

                yield Button("↺  Reset all services [0]", id="btn-reset-all", classes="btn-reset-all")

                yield Label("── log", classes="h")
                with Vertical(id="log-wrap"):
                    yield Log(id="log", auto_scroll=True)

        yield Footer()

    def on_mount(self):
        self._log("ready")
        self.set_interval(POLL_SECONDS, self._poll)
        self._poll()

    # ── Polling ──────────────────────────────────────────────────────────────

    @work
    async def _poll(self):
        for svc in SERVICES:
            try:
                r = await self._http.get(f"http://localhost:{svc['port']}/health")
                data = r.json()
            except Exception:
                data = None
            card = self._cards.get(svc["name"])
            if card:
                prev = card._last_status
                card.refresh_data(data)
                curr = data.get("status") if data else None
                if prev == "degraded" and curr == "healthy":
                    self._log(f"✓ {svc['name']} recovered — container restarted by MCP runner")

    # ── Button handler ────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed):
        b = event.button.id
        if   b == "btn-leak":        self.action_inject_leak()
        elif b == "btn-spike":       self.action_inject_spike()
        elif b == "btn-reset-leak":  self._hit(8001, "reset", "payment-service")
        elif b == "btn-reset-spike": self._hit(8003, "reset", "auth-service")
        elif b == "btn-reset-all":   self.action_reset_all()
        elif b == "btn-up":          self._compose("up --build -d", "starting…")
        elif b == "btn-down":        self._compose("down", "stopping…")
        elif b == "btn-restart":     self._compose("restart", "restarting…")

    # ── Key actions ──────────────────────────────────────────────────────────

    def action_inject_leak(self):  self._hit(8001, "leak",              "payment-service")
    def action_inject_spike(self): self._hit(8003, "spike?duration=600","auth-service")
    def action_reset_all(self):
        for svc in SERVICES: self._hit(svc["port"], "reset", svc["name"])
    def action_do_refresh(self):
        self._poll()
        self._log("refreshed")

    # ── Workers ──────────────────────────────────────────────────────────────

    @work
    async def _hit(self, port: int, endpoint: str, label: str):
        url = f"http://localhost:{port}/simulate/{endpoint}"
        self._log(f"→ {label}  {endpoint.split('?')[0]}")
        try:
            r = await self._http.post(url)
            r.raise_for_status()
            self._log(f"✓ {label}")
        except Exception as e:
            self._log(f"✗ {label}: {e}", err=True)
        self._poll()

    @work(exclusive=True)
    async def _compose(self, cmd: str, status: str):
        lbl = self.query_one("#compose-status", Label)
        lbl.update(status)
        self._log(f"$ docker compose {cmd}")
        proc = await asyncio.create_subprocess_shell(
            f"docker compose -f infra/docker-compose.yml {cmd}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout
        async for line in proc.stdout:
            t = line.decode().rstrip()
            if t: self._log(t)
        await proc.wait()
        code = proc.returncode
        lbl.update("✓ done" if code == 0 else f"✗ exit {code}")

    def _log(self, msg: str, err: bool = False):
        log = self.query_one("#log", Log)
        prefix = "✗" if err else "›"
        log.write_line(f"{_ts()}  {prefix}  {msg}")


if __name__ == "__main__":
    ControlPanel().run()
