# pages.py
from fastapi import APIRouter, Request, Cookie, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from landing_page_app.database import get_db
from landing_page_app.models.user import User 
from fastapi.templating import Jinja2Templates
from landing_page_app.models.clients import Client

router = APIRouter()
templates = Jinja2Templates(directory="landing_page_app/templates")

# Root redirect
@router.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")

# Login page
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Landing page (protected)
@router.get("/landing", response_class=HTMLResponse)
async def landing_page(request: Request, user_email: str | None = Cookie(None), db: Session = Depends(get_db)):
    if not user_email:
        return RedirectResponse("/login")
    user = db.query(User).filter(User.email == user_email).first()
    if not user or not user.is_active:
        return templates.TemplateResponse("login.html", {"request": request, "message": "Waiting for admin approval"})
    return templates.TemplateResponse("landing.html", {"request": request, "user": user})

# Extra protected pages
@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, user_email: str | None = Cookie(None)):
    if not user_email:
        return RedirectResponse("/login")
    return templates.TemplateResponse("search.html", {"request": request})

#clients 
@router.get("/clients/new-arrivals", response_class=HTMLResponse)
async def clients_new_arrivals(request: Request, user_email: str | None = Cookie(None), db: Session = Depends(get_db), message: str = ""):
    if not user_email:
        return RedirectResponse("/login")
    
    # Query all clients
    clients = db.query(Client).order_by(Client.created_at.desc()).all()
    active_count = db.query(Client).filter(Client.status == "active").count()
    inactive_count = db.query(Client).filter(Client.status == "inactive").count()
    
    return templates.TemplateResponse(
        "new_arrivals.html",
        {
            "request": request,
            "clients": clients,
            "active_count": active_count,
            "inactive_count": inactive_count,
            "message": message
        }
    )
