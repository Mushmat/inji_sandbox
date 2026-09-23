"""
Restarts the local Certify container and waits for it to come back healthy.

Needed after editing the identity CSV: the bundled data-provider plugin
loads the file once at container startup and doesn't re-read it per
request, so an edit only takes effect after a restart. Confirmed by testing
directly - editing the file alone did not change what got issued; a
restart did.
"""
import logging
import subprocess
import time

import requests

logger = logging.getLogger(__name__)

CONTAINER_NAME = "docker-compose-certify-1"
HEALTH_URL = "http://localhost:8090/v1/certify/.well-known/did.json"


def restart_certify(timeout: int = 300, poll_interval: int = 5, warmup: int = 10) -> bool:
    """Returns True once Certify is healthy again, False if it didn't come
    back within `timeout` seconds. Raises only if the restart command itself
    fails to run (e.g. Docker isn't up) - a slow-to-heal container is
    reported as a clean False, not an exception.

    Boot time under Rosetta emulation varies a lot (seen anywhere from ~2 to
    ~5 minutes for the same image), hence the generous default timeout. The
    `warmup` pause after the health check first passes exists because the
    health endpoint itself is cheap, but the first real issuance request
    right after a restart does actual key-loading work and can still time
    out for a few seconds even once Certify reports healthy.
    """
    subprocess.run(["docker", "restart", CONTAINER_NAME], check=True, capture_output=True, timeout=30)

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(HEALTH_URL, timeout=5)
            if r.status_code == 200:
                time.sleep(warmup)
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(poll_interval)

    logger.error("certify did not become healthy within %ss of restart", timeout)
    return False
