"""Context manager that patches all permission checks to pass for staff tests."""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

_BYPASS = ["bypass-role"]

_EFFECTIVE_ROLES_TARGETS = [
    "app.services.page_permissions.get_effective_roles",
    "app.routers.badges._helpers.get_effective_roles",
    "app.routers.assets.get_effective_roles",
    "app.routers.feedback.items.get_effective_roles",
    "app.routers.feedback.replies_reactions.get_effective_roles",
    "app.routers.content._helpers.get_effective_roles",
    "app.routers.staff._helpers.get_effective_roles",
    "app.routers.surveys._helpers.get_effective_roles",
    "app.routers.metrics._helpers.get_effective_roles",
    "app.routers.parties._helpers.get_effective_roles",
    "app.routers.runelite_configs._helpers.get_effective_roles",
    "app.routers.config.general.get_effective_roles",
    "app.routers.auth.session.get_effective_roles",
]


@contextmanager
def staff_permission_patches():
    """Patch every effective-roles lookup and bypass-roles fetch to return bypass-role."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch(
                "app.services.page_permissions.get_admin_bypass_roles",
                new_callable=AsyncMock,
                return_value=_BYPASS,
            )
        )
        for target in _EFFECTIVE_ROLES_TARGETS:
            stack.enter_context(
                patch(target, new_callable=AsyncMock, return_value=_BYPASS)
            )
        yield
