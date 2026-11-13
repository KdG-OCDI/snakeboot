"""What the tests on a PostgreSQL in a container of Docker share: whether Docker runs here, asked once per process."""

import functools
import subprocess


@functools.cache
def docker_runs() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
