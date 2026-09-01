"""Framework-neutral GUI presentation layer.

Qt widgets and workers are adapters around these state and localization contracts.
"""

from .i18n import Catalog, select_locale
from .workflow import GuiPresenter, GuiState, GuiStep, WorkflowStatus

__all__ = (
    "Catalog",
    "GuiPresenter",
    "GuiState",
    "GuiStep",
    "WorkflowStatus",
    "select_locale",
)
