# landing_page_app/core/template_config.py
"""
Shared Jinja2Templates configuration.
This version initializes lazily after app setup,
so it always detects FastAPI's static mount.
"""

from fastapi.templating import Jinja2Templates

_templates = None

def get_templates():
    """Return a shared Jinja2Templates instance (lazy-loaded)."""
    global _templates
    if _templates is None:
        _templates = Jinja2Templates(directory="landing_page_app/templates")
    return _templates
