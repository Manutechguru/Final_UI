from fastapi import APIRouter, Request, Depends, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.responses import JSONResponse
from fastapi import UploadFile, File
from sqlalchemy import desc
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
import uuid
import os
import re
import base64
from playwright.async_api import async_playwright


from landing_page_app.database import get_db
from landing_page_app.core.jinja import templates
from landing_page_app.models import (
    Invoice,
    InvoiceItem,
    InvoiceFile,
    InvoiceClient,
    User,
    UserRole,
)


# ==================================================
# ROUTER
# ==================================================
router = APIRouter(prefix="/admin/invoice", tags=["Invoice"])

# ==================================================
# HELPERS
# ==================================================
def require_admin(db: Session, user_email: str | None):
    if not user_email:
        return None
    user = db.query(User).filter(User.email == user_email).first()
    if not user or user.role != UserRole.ADMIN:
        return None
    return user

# ==================================================
# STEP 1: FORM (GET)
# ==================================================
@router.get("", response_class=HTMLResponse)
def invoice_form(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    if not require_admin(db, user_email):
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "invoice_form.html",
        {"request": request, "data": None},
    )

# ==================================================
# STEP 1B: FORM (POST FROM EDIT)
# ==================================================
@router.post("", response_class=HTMLResponse)
async def invoice_form_post(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    if not require_admin(db, user_email):
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    data = dict(form)

    return templates.TemplateResponse(
        "invoice_form.html",
        {
            "request": request,
            "data": data,
            "d": data,
        },
    )

# ==================================================
# STEP 2: PREVIEW
# ==================================================
@router.post("/preview", response_class=HTMLResponse)
async def invoice_preview(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),

    bill_from_address: str = Form(...),
    bill_to_address: str = Form(...),
    invoice_no: str = Form(...),
    invoice_date: str = Form(...),

    delivery_note: str = Form(None),
    payment_terms: str = Form(None),
    reference_no_date: str = Form(None),
    other_references: str = Form(None),

    buyers_order_no: str = Form(None),
    buyers_order_date: str = Form(None),

    dispatched_through: str = Form(None),
    destination: str = Form(None),

    leave_info: str = Form(None),

    particulars: str = Form(...),
    hsn_sac: str = Form(...),
    gst_rate: float = Form(...),
    amount: float = Form(...),

    total_amount: float = Form(...),
    amount_in_words: str = Form(...),

    account_holder_name: str = Form(...),
    bank_name: str = Form(...),
    account_no: str = Form(...),
    branch_ifsc: str = Form(...),
    signature_image: UploadFile = File(None),
):
    # ---------------- AUTH ----------------
    if not require_admin(db, user_email):
        return RedirectResponse("/login", status_code=302)
    
    # ---------------- FORM (READ ONCE) ----------------
    form = await request.form()
    client_bg = form.get("client_bg")
    existing_sig = form.get("signature_blob")

    signature_blob = None

    if signature_image:
        raw = await signature_image.read()
        if raw:
            signature_blob = base64.b64encode(raw).decode("utf-8")
    elif existing_sig:
        signature_blob = existing_sig


    bg_image = client_bg or ""

    # ---------------- GST ----------------
    gst_amount = round((amount * gst_rate) / 100, 2)

    # ---------------- REMARKS (STRICT RULE) ----------------
    # Remarks MUST always be Buyer's Order No.
    remarks = buyers_order_no or ""

    # ---------------- AUTO INVOICE LINE ----------------
    """
    Input:
    Professional services - Manu Sorapalli - 2377650
    01st Nov,2025 to 30th Nov,2025

    Output:
    Nov'25 Invoice - Manu Sorapalli
    """
    auto_invoice_line = ""

    try:
        lines = [l.strip() for l in particulars.splitlines() if l.strip()]

        # --- Extract Name ---
        # "Professional services - Manu Sorapalli - 2377650"
        header_parts = [p.strip() for p in lines[0].split("-")]
        person_name = header_parts[1]

        # --- Extract Start Date ---
        # "01st Nov,2025 to 30th Nov,2025"
        start_part = lines[1].split("to")[0].strip()

        # Remove ordinal suffix safely (01st → 01)
        start_part = re.sub(r"(st|nd|rd|th)", "", start_part)

        start_date = datetime.strptime(start_part, "%d %b,%Y")

        month_tag = start_date.strftime("%b'%y")
        auto_invoice_line = f"{month_tag} Invoice - {person_name}"

    except Exception:
        auto_invoice_line = ""

    # ---------------- DATA ----------------
    data = {
        "bill_from_address": bill_from_address,
        "bill_to_address": bill_to_address,
        "invoice_no": invoice_no,
        "invoice_date": invoice_date,

        "delivery_note": delivery_note,
        "payment_terms": payment_terms,
        "reference_no_date": reference_no_date,
        "other_references": other_references,

        "buyers_order_no": buyers_order_no,
        "buyers_order_date": buyers_order_date,

        "dispatched_through": dispatched_through,
        "destination": destination,

        # 🔥 CRITICAL FIX
        "remarks": remarks,                     # Buyer's Order No.
        "auto_invoice_line": auto_invoice_line, # Nov'25 Invoice - Name
        "leave_info": leave_info or "None",

        "particulars": particulars,
        "hsn_sac": hsn_sac,
        "gst_rate": gst_rate,
        "amount": amount,
        "gst_amount": gst_amount,
        "total_amount": total_amount,
        "amount_in_words": amount_in_words,

        "account_holder_name": account_holder_name,
        "bank_name": bank_name,
        "account_no": account_no,
        "branch_ifsc": branch_ifsc,
        "signature_blob": signature_blob,
    }
    
    return templates.TemplateResponse(
        "invoice_preview.html",
        {
            "request": request,
            "data": data,
            "bg_image": bg_image,
        },
    )


# ==================================================
# STEP 3: EXPORT PDF + SAVE DB
# ==================================================
@router.post("/export")
async def invoice_export(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin = require_admin(db, user_email)
    if not admin:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    data = dict(form)
    
    sig_base64 = data.get("signature_blob")

    sig_bytes = None
    sig_template = None

    if sig_base64:
        sig_bytes = base64.b64decode(sig_base64)   # for DB
        sig_template = sig_base64                  # for HTML


    # ---------- VALIDATION ----------
    required_keys = [
        "invoice_no",
        "invoice_date",
        "bill_from_address",
        "bill_to_address",
        "particulars",
        "amount",
        "total_amount",
        "amount_in_words",
        "account_holder_name",
        "bank_name",
        "account_no",
        "branch_ifsc",
    ]
    for k in required_keys:
        if k not in data:
            raise ValueError(f"Missing field: {k}")
    
    # ---------- DUPLICATE INVOICE CHECK ----------
    existing = (
        db.query(Invoice)
        .filter(Invoice.invoice_no == data["invoice_no"])
        .first()
    )

    if existing:
        return RedirectResponse(
            "/admin/invoice?msg=Invoice+number+already+exists",
            status_code=302,
        )
    
    # ---------- BACKGROUND IMAGE ----------
    bg_image = data.get("client_bg") or ""


    # ---------- RENDER HTML ----------
    html = templates.get_template("invoice_preview.html").render(
        request=request,
        data={**data, "signature_blob": sig_template},
        bg_image=bg_image,
    )
    
    debug_html = Path("debug_invoice.html")
    debug_html.write_text(html, encoding="utf-8")

    # ---------- OUTPUT ----------
    out_dir = Path("invoices")
    out_dir.mkdir(exist_ok=True)

    pdf_path = out_dir / f"{data['invoice_no']}-{uuid.uuid4().hex}.pdf"

    # ---------- PLAYWRIGHT (ASYNC) ----------
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(debug_html.resolve().as_uri(), wait_until="networkidle")

        await page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={
                "top": "0mm",
                "bottom": "0mm",
                "left": "0mm",
                "right": "0mm",
            },
        )

        await browser.close()

    # ---------- SAVE TO DB ----------
    invoice = Invoice(
        bill_from_address=data["bill_from_address"],
        bill_to_address=data["bill_to_address"],
        invoice_no=data["invoice_no"],
        invoice_date=datetime.strptime(data["invoice_date"], "%Y-%m-%d").date(),
        total_amount=float(data["total_amount"]),
        amount_in_words=data["amount_in_words"],
        account_holder_name=data["account_holder_name"],
        bank_name=data["bank_name"],
        account_no=data["account_no"],
        branch_ifsc=data["branch_ifsc"],
        signature_blob=sig_bytes,
        created_by=admin.id,
    )

    invoice.items.append(
        InvoiceItem(
            particulars=data["particulars"],
            hsn_sac=data["hsn_sac"],
            gst_rate=float(data["gst_rate"]),
            amount=float(data["amount"]),
        )
    )

    with open(pdf_path, "rb") as f:
        invoice.file = InvoiceFile(pdf_blob=f.read())

    db.add(invoice)
    db.commit()

    return RedirectResponse(
        "/admin?msg=Invoice+generated+successfully",
        status_code=302,
    )


@router.get("/generated")
def list_generated_invoices(
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin = require_admin(db, user_email)
    if not admin:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    invoices = (
        db.query(Invoice)
        .order_by(desc(Invoice.id))
        .all()
    )

    result = []
    for inv in invoices:
        result.append({
            "id": inv.id,
            "invoice_no_last3": inv.invoice_no[-3:],
        })

    return result

@router.get("/view/{invoice_id}")
def view_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin = require_admin(db, user_email)
    if not admin:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).get(invoice_id)
    if not invoice or not invoice.file:
        return Response("PDF not found", status_code=404)

    return Response(
        content=invoice.file.pdf_blob,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline; filename=invoice.pdf"
        }
    )
    
@router.get("/download/{invoice_id}")
def download_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin = require_admin(db, user_email)
    if not admin:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).get(invoice_id)
    if not invoice or not invoice.file:
        return Response("PDF not found", status_code=404)

    filename = f"{invoice.invoice_no}.pdf"

    return Response(
        content=invoice.file.pdf_blob,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@router.post("/client")
async def create_client(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
    bg_image: UploadFile = File(...),
    from_address: str = Form(...)
):
    admin = require_admin(db, user_email)
    if not admin:
        return JSONResponse(status_code=401)

    raw = await bg_image.read()
    
    exists = db.query(InvoiceClient)\
        .filter(InvoiceClient.from_address == from_address)\
        .first()

    if exists:
        return JSONResponse({"error": "duplicate"}, status_code=400)

    client = InvoiceClient(
        from_address=from_address,
        bg_blob=raw
    )

    db.add(client)
    db.commit()

    return {"status": "ok"}

@router.get("/clients")
def list_clients(
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin = require_admin(db, user_email)
    if not admin:
        return JSONResponse(status_code=401)

    clients = db.query(InvoiceClient).order_by(desc(InvoiceClient.id)).all()

    return [
        {
            "id": c.id,
            "from_address": c.from_address,
            "bg": base64.b64encode(c.bg_blob).decode()
        }
        for c in clients
    ]

@router.get("/signature/{sig_id}")
def serve_signature(sig_id: int, db: Session = Depends(get_db)):

    sig = db.query(InvoiceFile).get(sig_id)

    if not sig:
        return Response(status_code=404)

    return Response(
        content=sig.pdf_blob,
        media_type="image/png"
    )
