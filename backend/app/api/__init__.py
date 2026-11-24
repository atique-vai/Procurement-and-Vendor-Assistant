"""API route package and router aggregation."""

from importlib import import_module

from fastapi import APIRouter


router = APIRouter()

for _module_name in (
    "app.api.chat",
    "app.api.approvals",
    "app.api.graph_state",
):
    _module = import_module(_module_name)
    _module_router = getattr(_module, "router", None)
    if _module_router is not None:
        router.include_router(_module_router)


__all__ = ["router"]