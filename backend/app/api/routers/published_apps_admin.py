"""Published apps admin router composition.

This module keeps a stable import path while delegating implementations to
smaller, cohesive modules.
"""

from .published_apps_admin_shared import (
    BUILDER_MAX_FILE_BYTES,
    PublishedAppDraftDevRuntimeService,
    router,
)

# Ensure route modules are imported so decorators register on `router`.
from . import published_apps_admin_routes_apps as _routes_apps  # noqa: F401
from . import published_apps_admin_routes_builder as _routes_builder  # noqa: F401
from . import published_apps_admin_routes_coding_agent as _routes_coding_agent  # noqa: F401
from . import published_apps_admin_routes_publish as _routes_publish  # noqa: F401

from .published_apps_admin_builder_tools import (
    _apply_patch_operations_to_sandbox,
    _builder_tool_run_targeted_tests,
    _snapshot_files_from_sandbox,
)

__all__ = [
    "router",
    "BUILDER_MAX_FILE_BYTES",
    "PublishedAppDraftDevRuntimeService",
    "_builder_tool_run_targeted_tests",
    "_snapshot_files_from_sandbox",
    "_apply_patch_operations_to_sandbox",
]
