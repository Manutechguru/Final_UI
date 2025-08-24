# landing_page_app/routers/router.py
from landing_page_app.routers import auth, admin, status_history, templates as template_router
from landing_page_app.routers import uploadCSV

# clients sub-routers
from landing_page_app.routers.clients import base as clients_base
from landing_page_app.routers.clients import jobs as clients_jobs

# candidates sub-routers
from landing_page_app.routers.candidates import search as cand_search
from landing_page_app.routers.candidates import link as cand_link
from landing_page_app.routers.candidates import shortlist as cand_shortlist
from landing_page_app.routers.candidates import downloads as cand_downloads
from landing_page_app.routers.candidates import scoring as cand_scoring

# pages router
from landing_page_app.routers import pages

def include_routers(app):
    # Pages (HTML templates)
    app.include_router(pages.router)

    # Auth & Admin
    app.include_router(auth.router, tags=["Auth"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])

    # Clients
    app.include_router(clients_base.router, tags=["Clients"])
    app.include_router(clients_jobs.router,prefix="/clients", tags=["Client Jobs"])
    # Candidates
    app.include_router(cand_search.router, tags=["Candidates Search"])
    app.include_router(cand_link.router, tags=["Link Candidates"])
    app.include_router(cand_shortlist.router, tags=["Shortlist Candidates"])
    app.include_router(cand_downloads.router, tags=["Candidates Download"])
    app.include_router(cand_scoring.router, tags=["Candidates Scoring"])

    # Status, Templates, CSV Upload
    app.include_router(status_history.router, prefix="/status", tags=["Status History"])
    app.include_router(template_router.router, prefix="/templates", tags=["Templates"])
    app.include_router(uploadCSV.router)