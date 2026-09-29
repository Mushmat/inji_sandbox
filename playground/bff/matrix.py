"""The test matrix (FR14): every automated combination, one run after another.

"quick" runs each issuer, verifier and format once, honestly. "full" adds every tamper scenario.
Inji Web runs need a person, so they're left out; run those from the bench.
"""

import logging
import threading
import time
from datetime import datetime, timezone

import catalog
import runner

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_state = {"running": False, "preset": None, "total": 0, "done": 0, "current": None, "run_ids": [],
          "started_at": None, "finished_at": None, "cancelled": False, "error": None}


def combinations(preset: str) -> list:
    scenarios = ["none"] if preset == "quick" else list(catalog.SCENARIOS)
    out = []
    for issuer in catalog.ISSUERS:
        for wallet, w in catalog.WALLETS.items():
            if w["interactive"]:
                continue
            for verifier in catalog.VERIFIERS:
                for fmt in catalog.FORMATS:
                    for scenario in scenarios:
                        c = catalog.check(issuer, wallet, verifier, fmt, scenario)
                        # a format that can't be presented only needs recording once, not per tamper scenario
                        if not c["runnable"] or (c["limits"] and scenario != "none" and fmt == "mso_mdoc"):
                            continue
                        out.append({"issuer": issuer, "wallet": wallet, "verifier": verifier,
                                    "format": fmt, "scenario": scenario})
    return out


def status() -> dict:
    with _lock:
        return dict(_state, run_ids=list(_state["run_ids"]))


def start(preset: str) -> dict:
    combos = combinations(preset)
    with _lock:
        if _state["running"]:
            raise runner.RunBusy("The matrix is already running.")
        _state.update(running=True, preset=preset, total=len(combos), done=0, current=None, run_ids=[],
                      started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      finished_at=None, cancelled=False, error=None)
    threading.Thread(target=_work, args=(combos,), daemon=True).start()
    return status()


def cancel() -> dict:
    with _lock:
        _state["cancelled"] = True
    return status()


def _work(combos: list):
    try:
        for combo in combos:
            if _state["cancelled"]:
                break
            with _lock:
                _state["current"] = combo
            run = _start_when_free(combo)
            with _lock:
                _state["run_ids"].append(run["id"])
            while (runner.get(run["id"]) or {}).get("status") in ("running", "waiting"):
                if _state["cancelled"]:
                    runner.cancel(run["id"])
                    break
                time.sleep(1)
            with _lock:
                _state["done"] += 1
    except Exception as e:  # the matrix must end in a readable state, never stay "running"
        logger.exception("matrix stopped")
        _state["error"] = f"{type(e).__name__}: {e}"
    finally:
        with _lock:
            _state.update(running=False, current=None, finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _start_when_free(combo: dict) -> dict:
    """Waits out a run someone started from the bench, or a Certify restart, instead of failing."""
    deadline = time.monotonic() + 15 * 60
    while True:
        try:
            return runner.start(**{"fmt" if k == "format" else k: v for k, v in combo.items()})
        except runner.RunBusy:
            if time.monotonic() > deadline or _state["cancelled"]:
                raise
            time.sleep(3)
