"""Framework-neutral GUI presentation layer.

Qt widgets and workers are adapters around these state and localization contracts.
"""

from .i18n import Catalog, select_locale
from .qt_worker import PYSIDE_AVAILABLE, QtUnavailableError, require_pyside6
from .workflow import GuiPresenter, GuiState, GuiStep, WorkflowStatus

__all__ = (
    "Catalog",
    "GuiPresenter",
    "GuiState",
    "GuiStep",
    "PYSIDE_AVAILABLE",
    "QtUnavailableError",
    "WorkflowStatus",
    "require_pyside6",
    "select_locale",
)
