# landing_page_app/config.py
from fastapi.templating import Jinja2Templates
import os

templates = Jinja2Templates(directory=os.path.join("landing_page_app", "templates"))
