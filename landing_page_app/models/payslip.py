from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from datetime import datetime
from landing_page_app.database import Base


class Payslip(Base):
    __tablename__ = "payslips"

    id = Column(Integer, primary_key=True)

    # -------- HEADER DATA --------
    employee_code = Column(Text)
    employee_name = Column(Text)
    designation = Column(Text)
    bank_name = Column(Text)
    department = Column(Text)
    account_number = Column(Text)
    location = Column(Text)
    pan = Column(Text)
    pf_number = Column(Text)
    dob = Column(Text)
    uan = Column(Text)
    doj = Column(Text)
    lop_days = Column(Text)
    work_days = Column(Text)
    gender = Column(Text)
    regime_type = Column(Text)
    lop_reversal = Column(Text)
    pay_mode = Column(Text)
    payslip_month = Column(String)

    # -------- EARNINGS --------
    basic_salary = Column(Text)
    special_allowance = Column(Text)
    employer_pf = Column(Text)
    total_earnings = Column(Text)

    # -------- DEDUCTIONS --------
    pf = Column(Text)
    pf_arrears = Column(Text)
    professional_tax = Column(Text)
    total_deductions = Column(Text)

    # -------- FINAL --------
    net_pay = Column(Text)
    amount_words = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # ONE-TO-ONE FILE RELATION
    file = relationship(
        "PayslipFile",
        back_populates="payslip",
        uselist=False,
        cascade="all, delete-orphan"
    )


class PayslipFile(Base):
    __tablename__ = "payslip_files"

    id = Column(Integer, primary_key=True)

    payslip_id = Column(Integer, ForeignKey("payslips.id", ondelete="CASCADE"))

    pdf_path = Column(Text, nullable=False)
    stored_at = Column(DateTime, default=datetime.utcnow)

    payslip = relationship("Payslip", back_populates="file")
