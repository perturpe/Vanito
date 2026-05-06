#!/usr/bin/env python3
"""Vanito — Solana vanity wallet generator, interactive TUI app (Textual)."""

import base58
import nacl.signing
import os
import threading
import time
from multiprocessing import cpu_count

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, DataTable, Footer, Header, Input, Rule, Static


# ── constants ────────────────────────────────────────────────────────────────

WALLETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "found_wallets.txt")
VALID_B58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

DIFFICULTY_HINTS = [
    (0,  "",     ""),
    (1,  "Easy",     "[dim]Usually done in under a second[/dim]"),
    (2,  "Easy",     "[dim]A few seconds at most[/dim]"),
    (3,  "Moderate", "[dim]Typically 10–60 seconds[/dim]"),
    (4,  "Hard",     "[dim]Could take several minutes[/dim]"),
    (5,  "Very Hard","[dim]May take 30+ minutes[/dim]"),
    (99, "Extreme",  "[dim]Could take hours or days[/dim]"),
]


# ── mining workers ────────────────────────────────────────────────────────────

def _mine_thread(target_lower, stop_event, counter, counter_lock, result, result_lock):
    while not stop_event.is_set():
        sk        = nacl.signing.SigningKey.generate()
        pub_bytes = bytes(sk.verify_key)
        pubkey    = base58.b58encode(pub_bytes).decode()
        if pubkey.lower().startswith(target_lower):
            phantom_key = base58.b58encode(sk.encode() + pub_bytes).decode()
            with result_lock:
                if not result:
                    result.append((pubkey, phantom_key))
            stop_event.set()
            return
        with counter_lock:
            counter[0] += 1


# ── utilities ─────────────────────────────────────────────────────────────────

def fmt_time(s: float) -> str:
    if s < 60:   return f"{s:.0f}s"
    if s < 3600: return f"{s/60:.1f}m"
    return f"{s/3600:.1f}h"


def save_wallet(address: str, key: str) -> None:
    with open(WALLETS_FILE, "a") as f:
        f.write(f"Address: {address}\nKey: {key}\n---\n")


def notify(title: str, msg: str) -> None:
    os.system(
        f"osascript -e 'display notification \"{msg}\" "
        f"with title \"{title}\" sound name \"Crystal\"'"
    )


def copy_to_clipboard(text: str) -> bool:
    try:
        import subprocess
        subprocess.run("pbcopy", input=text.encode(), check=True)
        return True
    except Exception:
        return False


def load_wallets() -> list:
    if not os.path.exists(WALLETS_FILE):
        return []
    wallets = []
    with open(WALLETS_FILE) as f:
        content = f.read()
    for block in content.split("---"):
        block = block.strip()
        if not block:
            continue
        d = {}
        for line in block.splitlines():
            if line.startswith("Address: "): d["address"] = line[9:]
            elif line.startswith("Key: "):   d["key"] = line[5:]
        if "address" in d and "key" in d:
            wallets.append(d)
    return wallets


def difficulty_hint(length: int) -> tuple:
    """Return (label, description) for a given prefix length."""
    for min_len, label, desc in reversed(DIFFICULTY_HINTS):
        if length >= min_len:
            return label, desc
    return "", ""


# ── messages ──────────────────────────────────────────────────────────────────

class MiningUpdate(Message):
    def __init__(self, attempts: int, speed: float, elapsed: float) -> None:
        super().__init__()
        self.attempts = attempts
        self.speed    = speed
        self.elapsed  = elapsed


class MiningComplete(Message):
    def __init__(self, address: str, private_key: str, elapsed: float, attempts: int) -> None:
        super().__init__()
        self.address     = address
        self.private_key = private_key
        self.elapsed     = elapsed
        self.attempts    = attempts


# ── app ───────────────────────────────────────────────────────────────────────

class VanityMinerApp(App):
    TITLE = "Vanito"

    CSS = """
    Screen { background: #07101e; }
    Header { background: #091525; color: #38a3d4; text-style: bold; }
    Footer { background: #091525; color: #1f3a52; }
    .view  { width: 1fr; height: 1fr; }


    /* ════════════ HOME ════════════ */
    #home-view { align: center middle; }

    #home-card {
        width: 58;
        padding: 2 4;
        background: #0a1828;
        border: round #14304d;
    }

    #logo      { text-align: center; color: #38a3d4; text-style: bold; }
    #tagline   { text-align: center; color: #1d3650; margin-bottom: 1; }

    #prefix-label {
        color: #4a87b8;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
        height: 1;
    }

    #prefix-input {
        border: round #14304d;
        background: #050d18;
        color: #a8c8e8;
        margin-bottom: 1;
    }
    #prefix-input:focus { border: round #1a76b5; }

    #diff-hint {
        height: 1;
        margin-bottom: 1;
        color: #4a87b8;
        text-align: center;
    }

    #input-error {
        color: #c0392b;
        text-align: center;
        text-style: bold;
        display: none;
        height: 1;
        margin-bottom: 1;
    }

    #start-btn {
        width: 100%;
        margin-top: 1;
        margin-bottom: 1;
        background: #145a8c;
        color: #cce8f8;
        text-style: bold;
        border: tall #1a76b5;
    }
    #start-btn:hover { background: #1a76b5; color: #ffffff; }

    #history-btn {
        width: 100%;
        background: transparent;
        color: #1f3a52;
        border: round #112234;
    }
    #history-btn:hover { background: #0d1e30; color: #2d6a9f; }

    #wallet-count {
        text-align: center;
        color: #1d3650;
        margin-top: 1;
        height: 1;
    }

    #home-tip {
        text-align: center;
        color: #142030;
        margin-top: 1;
        height: 1;
    }


    /* ════════════ MINING ════════════ */
    #mining-view { align: center middle; display: none; }

    #mining-card {
        width: 58;
        padding: 2 4;
        background: #0a1828;
        border: round #1a76b5;
    }

    #mining-header   { text-align: center; color: #38a3d4; text-style: bold; margin-bottom: 0; }
    #mining-subtitle { text-align: center; color: #1d3650; margin-bottom: 1; height: 1; }

    #stats-grid { height: auto; margin: 1 0; }
    .stat-col   { width: 1fr; padding-right: 2; }
    .stat-block { height: 3; margin-bottom: 1; }
    .stat-label { color: #1f3a52; text-style: bold; height: 1; }
    .stat-value { color: #7bbcdc; height: 1; }

    #prog-section { margin: 1 0 0 0; }
    #prog-label   { color: #1f3a52; text-style: bold; height: 1; margin-bottom: 1; }
    #progress-bar { height: 1; }

    #cancel-btn {
        width: 100%;
        margin-top: 2;
        background: #1a0808;
        color: #c06060;
        border: round #3d1010;
        text-style: bold;
    }
    #cancel-btn:hover { background: #8b1c1c; color: #ffd0d0; border: round #b71c1c; }


    /* ════════════ RESULT ════════════ */
    #result-view { align: center middle; display: none; }

    #result-card {
        width: 64;
        padding: 2 4;
        background: #0a1828;
        border: round #1a5c2a;
    }

    #result-header   { text-align: center; color: #4caf7d; text-style: bold; }
    #result-subtitle { text-align: center; color: #193d26; height: 1; margin-bottom: 1; }

    /* address section */
    #addr-section { margin-top: 1; }
    #addr-step    { color: #1a76b5; text-style: bold; height: 1; }
    #addr-desc    { color: #1d3650; height: 1; margin-bottom: 1; }

    /* key section */
    #key-section  { margin-top: 1; }
    #key-step     { color: #b8860b; text-style: bold; height: 1; }
    #key-desc     { color: #1d3650; height: 1; margin-bottom: 1; }

    .res-row   { height: 3; margin-bottom: 1; }

    .res-value {
        color: #76c7a8;
        background: #050d18;
        border: round #14402a;
        padding: 0 1;
        width: 1fr;
        height: 3;
    }

    .copy-btn {
        width: 10;
        height: 3;
        margin-left: 1;
        background: #0d2030;
        color: #2d6a9f;
        border: round #112234;
        text-style: bold;
    }
    .copy-btn:hover  { background: #1a76b5; color: #ffffff; border: round #1a76b5; }
    .copy-btn.copied { background: #1b5e20; color: #66bb6a; border: round #2e7d32; }

    #result-warning {
        text-align: center;
        color: #7a5500;
        height: 1;
        margin: 1 0;
    }

    #phantom-tip {
        text-align: center;
        color: #1a3050;
        height: 1;
        margin-bottom: 1;
    }

    #result-meta {
        text-align: center;
        color: #142028;
        height: 1;
    }

    #result-btns { height: 3; margin-top: 1; }

    #mine-again-btn {
        width: 1fr;
        background: #145a8c;
        color: #cce8f8;
        text-style: bold;
        border: tall #1a76b5;
        margin-right: 1;
    }
    #mine-again-btn:hover { background: #1a76b5; color: #ffffff; }

    #result-history-btn {
        width: 1fr;
        background: transparent;
        color: #1f3a52;
        border: round #112234;
    }
    #result-history-btn:hover { background: #0d1e30; color: #2d6a9f; }


    /* ════════════ HISTORY ════════════ */
    #history-view { padding: 1 3; display: none; }

    #hist-top {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }

    #hist-title {
        color: #38a3d4;
        text-style: bold;
        width: 1fr;
        content-align: center middle;
    }

    #hist-note {
        text-align: center;
        color: #1d3650;
        height: 1;
        margin-bottom: 1;
    }

    #back-btn {
        width: 14;
        background: transparent;
        color: #1f3a52;
        border: round #112234;
    }
    #back-btn:hover { background: #0d1e30; color: #2d6a9f; }

    DataTable { height: 1fr; }
    """

    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._stop_event      = None
        self._processes: list = []
        self._current_target  = ""

    # ── layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # ── Home ──────────────────────────────────────────────────────────────
        with Container(id="home-view", classes="view"):
            with Container(id="home-card"):
                yield Static("VANITO", id="logo")
                yield Static("Give your Solana wallet a custom address", id="tagline")
                yield Rule()
                yield Static(
                    "What do you want your address to start with?",
                    id="prefix-label",
                )
                yield Input(
                    placeholder="e.g.  cat   doge   OM   PEPE",
                    id="prefix-input",
                    max_length=7,
                )
                yield Static("", id="diff-hint")
                yield Static("", id="input-error")
                yield Button("Generate My Wallet", id="start-btn")
                yield Button("My Saved Wallets", id="history-btn")
                yield Static("", id="wallet-count")
                yield Static(
                    "[dim]Tip: 1-3 letters generates in seconds[/dim]",
                    id="home-tip",
                )

        # ── Mining ────────────────────────────────────────────────────────────
        with Container(id="mining-view", classes="view"):
            with Container(id="mining-card"):
                yield Static("Searching...", id="mining-header")
                yield Static(
                    "Checking millions of addresses for your match",
                    id="mining-subtitle",
                )
                yield Rule()
                with Horizontal(id="stats-grid"):
                    with Vertical(classes="stat-col"):
                        with Vertical(classes="stat-block"):
                            yield Static("Looking for",        classes="stat-label")
                            yield Static("—", id="stat-target",     classes="stat-value")
                        with Vertical(classes="stat-block"):
                            yield Static("Addresses checked",  classes="stat-label")
                            yield Static("0", id="stat-attempts",   classes="stat-value")
                    with Vertical(classes="stat-col"):
                        with Vertical(classes="stat-block"):
                            yield Static("Speed",              classes="stat-label")
                            yield Static("—", id="stat-speed",      classes="stat-value")
                        with Vertical(classes="stat-block"):
                            yield Static("Est. time left",     classes="stat-label")
                            yield Static("Calculating...", id="stat-eta", classes="stat-value")
                with Vertical(id="prog-section"):
                    yield Static("Progress", id="prog-label")
                    yield Static("",         id="progress-bar")
                yield Button("Stop Searching", id="cancel-btn")

        # ── Result ────────────────────────────────────────────────────────────
        with Container(id="result-view", classes="view"):
            with Container(id="result-card"):
                yield Static("Your Wallet Is Ready!", id="result-header")
                yield Static("Saved automatically to found_wallets.txt", id="result-subtitle")
                yield Rule()

                with Vertical(id="addr-section"):
                    yield Static("STEP 1 - Your Wallet Address", id="addr-step")
                    yield Static(
                        "Safe to share — give this to anyone sending you SOL",
                        id="addr-desc",
                    )
                    with Horizontal(classes="res-row"):
                        yield Static("", id="result-address", classes="res-value")
                        yield Button("Copy", id="copy-address-btn", classes="copy-btn")

                with Vertical(id="key-section"):
                    yield Static("STEP 2 - Your Import Key", id="key-step")
                    yield Static(
                        "Paste this into Phantom: Settings > Import Wallet",
                        id="key-desc",
                    )
                    with Horizontal(classes="res-row"):
                        yield Static("", id="result-key", classes="res-value")
                        yield Button("Copy", id="copy-key-btn", classes="copy-btn")

                yield Static(
                    "Never share your Import Key with anyone",
                    id="result-warning",
                )
                yield Static("", id="result-meta")

                with Horizontal(id="result-btns"):
                    yield Button("Generate Another", id="mine-again-btn")
                    yield Button("My Saved Wallets", id="result-history-btn")

        # ── History ───────────────────────────────────────────────────────────
        with Container(id="history-view", classes="view"):
            with Horizontal(id="hist-top"):
                yield Button("<- Back", id="back-btn")
                yield Static("My Saved Wallets", id="hist-title")
            yield Static(
                "All wallets are also saved in found_wallets.txt on your Desktop",
                id="hist-note",
            )
            yield DataTable(id="history-table", cursor_type="row")

        yield Footer()

    def on_mount(self) -> None:
        self._refresh_count()

    # ── view routing ──────────────────────────────────────────────────────────

    def _show(self, view_id: str) -> None:
        for v in ("home-view", "mining-view", "result-view", "history-view"):
            self.query_one(f"#{v}").display = (v == view_id)

    def _refresh_count(self) -> None:
        n = len(load_wallets())
        self.query_one("#wallet-count").update(
            f"[dim]{n} wallet{'s' if n != 1 else ''} saved[/dim]"
        )

    # ── input live feedback ───────────────────────────────────────────────────

    @on(Input.Changed, "#prefix-input")
    def handle_input_change(self, event: Input.Changed) -> None:
        text = event.value.strip()
        hint = self.query_one("#diff-hint")
        err  = self.query_one("#input-error")

        if not text:
            hint.update("")
            return

        invalid = [c for c in text if c not in VALID_B58]
        if invalid:
            hint.update("")
            err.update(f"Remove invalid characters: {''.join(set(invalid))}")
            err.display = True
            return

        err.display = False
        label, desc = difficulty_hint(len(text))
        colors = {
            "Easy":      "#4caf7d",
            "Moderate":  "#e8c84a",
            "Hard":      "#e07030",
            "Very Hard": "#c04040",
            "Extreme":   "#a02020",
        }
        color = colors.get(label, "#4a87b8")
        hint.update(f"[bold {color}]{label}[/bold {color}]  {desc}")

    # ── button handlers ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#start-btn")
    def handle_start(self) -> None:
        inp    = self.query_one("#prefix-input", Input)
        target = inp.value.strip()
        err    = self.query_one("#input-error")

        if not target:
            err.update("Please type at least one letter.")
            err.display = True
            return
        if not all(c in VALID_B58 for c in target):
            err.update("Some characters aren't allowed. Use letters and numbers only (no 0, O, I, l).")
            err.display = True
            return

        err.display = False
        self._current_target = target
        self._init_stats(target)
        self._show("mining-view")
        self._run_miner(target)

    @on(Button.Pressed, "#cancel-btn")
    def handle_cancel(self) -> None:
        self._stop_all()
        self._show("home-view")

    @on(Button.Pressed, "#mine-again-btn")
    def handle_mine_again(self) -> None:
        self.query_one("#prefix-input", Input).value = ""
        self.query_one("#diff-hint").update("")
        self._show("home-view")
        self._refresh_count()

    @on(Button.Pressed, "#copy-address-btn")
    def handle_copy_address(self) -> None:
        text = str(self.query_one("#result-address", Static).renderable)
        self._do_copy(text, "#copy-address-btn")

    @on(Button.Pressed, "#copy-key-btn")
    def handle_copy_key(self) -> None:
        text = str(self.query_one("#result-key", Static).renderable)
        self._do_copy(text, "#copy-key-btn")

    def _do_copy(self, text: str, btn_id: str) -> None:
        if not copy_to_clipboard(text):
            return
        btn = self.query_one(btn_id, Button)
        btn.label = "Copied!"
        btn.add_class("copied")
        self.set_timer(1.5, lambda: self._reset_copy_btn(btn_id))

    def _reset_copy_btn(self, btn_id: str) -> None:
        btn = self.query_one(btn_id, Button)
        btn.label = "Copy"
        btn.remove_class("copied")

    @on(Button.Pressed, "#history-btn")
    @on(Button.Pressed, "#result-history-btn")
    def handle_show_history(self) -> None:
        self._populate_history()
        self._show("history-view")

    @on(Button.Pressed, "#back-btn")
    def handle_back(self) -> None:
        self._show("home-view")

    # ── mining ────────────────────────────────────────────────────────────────

    def _init_stats(self, target: str) -> None:
        self.query_one("#stat-target").update(f"[bold #e8c84a]{target}...[/]")
        self.query_one("#stat-attempts").update("0")
        self.query_one("#stat-speed").update("—")
        self.query_one("#stat-eta").update("Calculating...")
        self.query_one("#progress-bar").update("")

    def _stop_all(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        self._processes.clear()

    @work(thread=True)
    def _run_miner(self, target: str) -> None:
        cores        = cpu_count()
        stop_event   = threading.Event()
        counter      = [0]
        counter_lock = threading.Lock()
        result: list = []
        result_lock  = threading.Lock()

        self._stop_event = stop_event

        threads = [
            threading.Thread(
                target=_mine_thread,
                args=(target.lower(), stop_event, counter, counter_lock, result, result_lock),
                daemon=True,
            )
            for _ in range(cores)
        ]
        self._processes = threads
        for t in threads:
            t.start()

        start      = time.time()
        difficulty = 58 ** len(target)

        while not stop_event.is_set():
            time.sleep(0.25)
            elapsed  = time.time() - start
            attempts = counter[0]
            speed    = attempts / elapsed if elapsed > 0 else 0
            self.post_message(MiningUpdate(attempts, speed, elapsed))

        for t in threads:
            t.join(timeout=0.5)
        self._processes.clear()

        if result:
            address, phantom_key = result[0]
            elapsed = time.time() - start
            save_wallet(address, phantom_key)
            notify("Wallet Ready!", f"Your address starts with '{target}'")
            self.post_message(MiningComplete(address, phantom_key, elapsed, counter[0]))

    # ── live updates ──────────────────────────────────────────────────────────

    def on_mining_update(self, msg: MiningUpdate) -> None:
        target = self._current_target
        if not target:
            return
        difficulty = 58 ** len(target)
        ratio      = min(msg.attempts / difficulty, 1.0) if difficulty > 0 else 0

        self.query_one("#stat-attempts").update(f"{msg.attempts:,}")
        self.query_one("#stat-speed").update(f"[#4caf7d]{msg.speed:,.0f}[/] / sec")

        if msg.speed > 0:
            eta = max((difficulty - msg.attempts) / msg.speed, 0)
            self.query_one("#stat-eta").update(f"[#38a3d4]{fmt_time(eta)}[/]")

        width  = 38
        filled = int(width * ratio)
        bar = (
            f"[#1a76b5]{'█' * filled}[/]"
            f"[#0d1e30]{'█' * (width - filled)}[/]"
            f"  [bold]{ratio * 100:.1f}%[/bold]"
        )
        self.query_one("#progress-bar").update(bar)

    def on_mining_complete(self, msg: MiningComplete) -> None:
        self.query_one("#result-address").update(msg.address)
        self.query_one("#result-key").update(msg.private_key)
        self.query_one("#result-meta").update(
            f"[dim]Found in {fmt_time(msg.elapsed)} — {msg.attempts:,} addresses checked[/dim]"
        )
        self._show("result-view")

    # ── history ───────────────────────────────────────────────────────────────

    def _populate_history(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Wallet Address", "Saved")
        wallets = load_wallets()
        if not wallets:
            table.add_row("No wallets saved yet — generate one first!", "")
            return
        for w in reversed(wallets):
            table.add_row(w["address"], "tap to copy key")

    @on(DataTable.RowSelected, "#history-table")
    def handle_history_row(self, event: DataTable.RowSelected) -> None:
        wallets = list(reversed(load_wallets()))
        idx = event.cursor_row
        if idx >= len(wallets):
            return
        key = wallets[idx]["key"]
        if copy_to_clipboard(key):
            self.query_one("#hist-note").update(
                "[bold #4caf7d]Import Key copied to clipboard![/bold #4caf7d]"
            )
            self.set_timer(
                2.5,
                lambda: self.query_one("#hist-note").update(
                    "Tap any row to copy its Import Key to your clipboard"
                ),
            )

    def on_unmount(self) -> None:
        self._stop_all()


if __name__ == "__main__":
    VanityMinerApp().run()
