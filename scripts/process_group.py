"""Terminate a launched process group with bounded waits, shared by every launcher and capture."""

import os
import signal
import subprocess


def stop_group(process):
    """Terminate the whole process group with bounded waits; returns cleanup errors."""
    errors = []

    def send(sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except OSError as error:
            errors.append(f"{type(error).__name__}: {error}")

    send(signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        pass
    except OSError as error:
        errors.append(f"Cleanup {type(error).__name__}: {error}")
    # A child may survive even after the group leader exits.
    send(signal.SIGKILL)
    try:
        process.wait(timeout=5)
    except (subprocess.TimeoutExpired, KeyboardInterrupt, OSError) as error:
        errors.append(f"Cleanup {type(error).__name__}: {error}")
    return errors
