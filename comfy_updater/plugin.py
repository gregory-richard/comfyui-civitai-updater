from __future__ import annotations

from pathlib import Path

from .config_store import ConfigStore
from .jobs import JobManager
from .routes import register_routes
from .updater_service import UpdaterService

_INITIALIZED = False


def initialize_plugin() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    root_dir = Path(__file__).resolve().parents[1]
    data_dir = root_dir / ".civitai_updater"

    config_store = ConfigStore(data_dir)
    updater_service = UpdaterService(config_store)
    job_manager = JobManager()
    register_routes(config_store, updater_service, job_manager)

    _INITIALIZED = True

