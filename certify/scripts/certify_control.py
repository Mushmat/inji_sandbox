"""
Restarts the local Certify container in the background and exposes its
progress so a UI can show a live "still restarting" state instead of either
blocking for minutes or reporting a false failure.

Needed after editing the identity CSV: the bundled data-provider plugin
loads the file once at container startup and doesn't re-read it per
request, so an edit only takes effect after a restart. Confirmed by testing
directly - editing the file alone did not change what got issued; a
restart did.

Boot time under Rosetta emulation depends heavily on host load, not just
the container itself - seen anywhere from ~2 to ~9 minutes for the same
image on the same machine. A blocking call with a fixed timeout has no good
answer for "still going, just slow" - it either blocks the caller for
minutes or has to guess a cutoff and sometimes guesses wrong. Polling this
module's status instead lets the caller show real progress and only call it
a problem once it's actually been too long.
"""
import logging
import subprocess
import threading
import time

import requests

logger = logging.getLogger(__name__)

CONTAINER_NAME = "docker-compose-certify-1"
HEALTH_URL = "http://localhost:8090/v1/certify/.well-known/did.json"
STUCK_AFTER = 900  # seconds - past this, it's a real problem, not "just slow"

_lock = threading.Lock()
_state = {"restarting": False, "healthy": True, "started_at": None, "error": None}


def get_status() -> dict:
    with _lock:
        status = dict(_state)
    if status["restarting"] and status["started_at"]:
        status["elapsed"] = round(time.time() - status["started_at"])
        status["stuck"] = status["elapsed"] > STUCK_AFTER
    else:
        status["elapsed"] = 0
        status["stuck"] = False
    return status


def _run(poll_interval: int, warmup: int):
    try:
        subprocess.run(["docker", "restart", CONTAINER_NAME], check=True, capture_output=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.exception("docker restart command itself failed")
        with _lock:
            _state.update(restarting=False, error=f"docker restart failed: {e}")
        return

    while True:
        try:
            r = requests.get(HEALTH_URL, timeout=5)
            if r.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(poll_interval)

    # health endpoint is cheap; the first real signing request right after a
    # restart is not, so give it a moment before declaring done
    time.sleep(warmup)
    with _lock:
        _state.update(restarting=False, healthy=True, error=None)


def start_restart(poll_interval: int = 5, warmup: int = 10) -> bool:
    """Kicks off a restart in the background and returns immediately.
    Returns False (does nothing) if a restart is already in progress rather
    than starting a second one against the same container."""
    with _lock:
        if _state["restarting"]:
            return False
        _state.update(restarting=True, healthy=False, started_at=time.time(), error=None)

    thread = threading.Thread(target=_run, args=(poll_interval, warmup), daemon=True)
    thread.start()
    return True
