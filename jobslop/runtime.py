"""Shared state of the running app (port, the job being applied to, when the extension was last seen)."""

from jobslop.config import APP_PORT

state = {"port": APP_PORT, "active": None, "ext_seen": 0.0}
