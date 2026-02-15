"""Published apps admin router composition.

This module keeps a stable import path while delegating implementations to
smaller, cohesive modules.
"""

from .published_apps_admin_shared import (
    BUILDER_MAX_FILE_BYTES,
    BuilderPatchGenerationResult,
    BuilderPatchOp,
    PublishedAppDraftDevRuntimeService,
    router,
)

# Ensure route modules are imported so decorators register on `router`.
from . import published_apps_admin_routes_apps as _routes_apps  # noqa: F401
from . import published_apps_admin_routes_builder as _routes_builder  # noqa: F401
from . import published_apps_admin_routes_chat as _routes_chat  # noqa: F401
from . import published_apps_admin_routes_publish as _routes_publish  # noqa: F401

# Re-export helper functions used by internal tests for monkeypatching.
from .published_apps_admin_builder_model import _generate_builder_patch_with_model
from .published_apps_admin_builder_patch import _build_builder_patch_from_prompt
from .published_apps_admin_builder_core import _run_worker_build_preflight
from .published_apps_admin_builder_tools import (
    _apply_patch_operations_to_sandbox,
    _builder_tool_run_targeted_tests,
    _snapshot_files_from_sandbox,
)

__all__ = [
    "router",
    "BUILDER_MAX_FILE_BYTES",
    "BuilderPatchGenerationResult",
    "BuilderPatchOp",
    "PublishedAppDraftDevRuntimeService",
    "_build_builder_patch_from_prompt",
    "_generate_builder_patch_with_model",
    "_run_worker_build_preflight",
    "_builder_tool_run_targeted_tests",
    "_snapshot_files_from_sandbox",
    "_apply_patch_operations_to_sandbox",
]
