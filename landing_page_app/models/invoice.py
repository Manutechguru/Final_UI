from sqlalchemy import (
    Column, Integer, String, Text, Date, Numeric,
    ForeignKey, LargeBinary, DateTime, LargeBinary
)
from sqlalchemy.orm import relationship
from datetime import datetime
from landing_page_app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)

    # Header – Left / Right blocks
    bill_from_address = Column(Text, nullable=False)
    bill_to_address = Column(Text, nullable=False)

    invoice_no = Column(String(100), nullable=False, unique=True)
    invoice_date = Column(Date, nullable=False)

    delivery_note = Column(String(200))
    payment_terms = Column(String(200))
    reference_no_date = Column(String(200))
    other_references = Column(String(200))

    buyers_order_no = Column(String(200))
    buyers_order_date = Column(Date)

    dispatched_through = Column(String(200))
    destination = Column(String(200))

    remarks = Column(Text)
    leave_info = Column(String(100))

    # Totals
    total_amount = Column(Numeric(12, 2), nullable=False)
    amount_in_words = Column(Text, nullable=False)

    # Bank
    account_holder_name = Column(String(200), nullable=False)
    bank_name = Column(String(200), nullable=False)
    account_no = Column(String(50), nullable=False)
    branch_ifsc = Column(String(100), nullable=False)
    signature_blob = Column(LargeBinary, nullable=True)

    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan"
    )

    file = relationship(
        "InvoiceFile",
        back_populates="invoice",
        uselist=False
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))

    particulars = Column(Text, nullable=False)
    hsn_sac = Column(String(50), nullable=False)
    gst_rate = Column(Numeric(5, 2), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="items")


class InvoiceFile(Base):
    __tablename__ = "invoice_files"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))

    pdf_blob = Column(LargeBinary, nullable=False)
    stored_at = Column(DateTime, default=datetime.utcnow)

    invoice = relationship("Invoice", back_populates="file")


class InvoiceClient(Base):
    __tablename__ = "invoice_clients"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    from_address = Column(Text, nullable=False)
    to_address = Column(Text, nullable=True)
    bg_blob = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
