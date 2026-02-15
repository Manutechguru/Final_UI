from fastapi import APIRouter, Depends, Request, Cookie, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
import subprocess
import sys
import uuid
import tempfile
import calendar

from landing_page_app.database import get_db
from landing_page_app.core.jinja import templates
from landing_page_app.models.payslip import Payslip, PayslipFile
from landing_page_app.models.user import User, UserRole

router = APIRouter(tags=["Payslip"])
BASE_DIR = Path(__file__).resolve().parent.parent
LOGO_PATH = BASE_DIR / "static" / "logo.png"
LOGO_URL = "/static/logo.png"



# ---------------- helpers (copied logic from admin.py, NOT touching admin.py) ----------------

def _is_admin(user: User) -> bool:
    role = getattr(user, "role", None)
    try:
        return role == UserRole.ADMIN
    except Exception:
        return str(role).upper() == "ADMIN"


def _require_admin(db: Session, user_email: str | None):
    if not user_email:
        return None, RedirectResponse(url="/login?next=/admin/payslip", status_code=302)

    admin = db.query(User).filter(User.email == user_email).first()

    if not admin:
        return None, RedirectResponse(url="/login?next=/admin/payslip", status_code=302)

    if not _is_admin(admin):
        return None, RedirectResponse(url="/templates/?error=access_denied", status_code=302)

    return admin, None


# ============================ PAYSLIP ROUTES ============================
@router.get("/admin/payslip", response_class=HTMLResponse)
def payslip_form(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
    slip_id: int | None = Query(None),
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    slips = db.query(Payslip).order_by(Payslip.created_at.desc()).all()

    data = {}

    if slip_id:
        slip = db.get(Payslip, slip_id)
        if slip:
            data = {c.name: getattr(slip, c.name) for c in slip.__table__.columns}

    return templates.TemplateResponse(
        "payslip_form.html",
        {
            "request": request,
            "admin": admin,
            "slips": slips,
            "d": data,   # 👈 THIS is the magic
        },
    )


@router.post("/admin/payslip/preview", response_class=HTMLResponse)
async def payslip_preview(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    form = await request.form()
    payload = dict(form)

    # ================= AUTO WORK DAYS =================
    # payslip_month format: YYYY-MM
    year, month = payload["payslip_month"].split("-")

    year = int(year)
    month = int(month)

    # real calendar days (handles Feb + leap year)
    work_days = calendar.monthrange(year, month)[1]

    # FORCE overwrite whatever frontend sent
    payload["work_days"] = work_days
    # =================================================

    slip = Payslip(**payload)

    db.add(slip)
    db.commit()
    db.refresh(slip)

    return templates.TemplateResponse(
        "payslip_preview.html",
        {
            "request": request,
            "slip": slip,
            "logo_path": str(LOGO_PATH),
            "logo_url": LOGO_URL,
        },
    )



@router.post("/admin/payslip/export/{slip_id}")
def payslip_export(
    slip_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    slip = db.get(Payslip, slip_id)
    if not slip:
        raise HTTPException(status_code=404, detail="Payslip not found")

    tmp_dir = Path(tempfile.gettempdir())

    html_path = tmp_dir / f"payslip_{slip_id}.html"
    pdf_path = tmp_dir / f"payslip_{uuid.uuid4()}.pdf"

    rendered_html = templates.get_template("payslip_preview.html").render(
        {
            "slip": slip,
            "logo_path": str(LOGO_PATH),
        }
    )

    html_path.write_text(rendered_html, encoding="utf-8")

    # EXACT same Playwright flow you already use for invoice
    subprocess.run(
        [
            sys.executable,
            "landing_page_app/pdf_worker.py",
            str(html_path),
            str(pdf_path),
        ],
        check=True,
    )


    file_row = PayslipFile(
        payslip_id=slip.id,
        pdf_path=str(pdf_path),
    )

    db.add(file_row)
    db.commit()

    return RedirectResponse("/admin/payslip", status_code=302)


@router.get("/admin/payslip/file/{slip_id}")
def view_payslip_pdf(
    slip_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    slip = db.get(Payslip, slip_id)

    if not slip or not slip.file:
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(slip.file.pdf_path, media_type="application/pdf")


@router.get("/admin/payslip/download/{slip_id}")
def download_payslip_pdf(
    slip_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    slip = db.get(Payslip, slip_id)

    if not slip or not slip.file:
        raise HTTPException(status_code=404, detail="PDF not found")

    # ===== FILENAME LOGIC =====

    # payslip_month format: YYYY-MM
    year, month = slip.payslip_month.split("-")

    month_map = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
    }

    mon = month_map.get(month, month)

    filename = f"{slip.employee_code}-{mon}{year}-Payslip.pdf"

    # ===========================

    return FileResponse(
        slip.file.pdf_path,
        filename=filename,
        media_type="application/pdf",
    )