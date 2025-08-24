# landing_page_app/utils/xlsx_utils.py

import os
from io import BytesIO
from typing import List, Dict
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


# -----------------------------
# Helper to Create XLSX Workbook
# -----------------------------
def create_xlsx(data: List[Dict], columns: List[str], sheet_name: str = "Sheet1") -> BytesIO:
    """
    Creates an in-memory XLSX file from provided data.
    
    Args:
        data: List of dictionaries where keys are column names.
        columns: Column names in the order they should appear.
        sheet_name: Sheet name (default = "Sheet1")
    Returns:
        BytesIO object (in-memory XLSX)
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    # Styling for header
    header_font = Font(bold=True)
    center_align = Alignment(horizontal="center", vertical="center")

    # Add headers
    ws.append(columns)
    for col in ws[1]:
        col.font = header_font
        col.alignment = center_align

    # Add rows of data
    for row in data:
        ws.append([row.get(col, "") for col in columns])

    # Auto-adjust column widths
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max_length + 2

    # Save in memory
    file_stream = BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    return file_stream


# -----------------------------
# Candidate XLSX Export
# -----------------------------
def export_candidates_xlsx(candidates: List[Dict]) -> BytesIO:
    """
    Export candidate data to XLSX.
    """
    columns = [
        "Candidate ID", "Candidate Name", "Email", "Contact", "Location",
        "Skillset", "Education", "Company", "Resume Link", "Status"
    ]
    return create_xlsx(candidates, columns, sheet_name="Candidates")


# -----------------------------
# Jobs XLSX Export
# -----------------------------
def export_jobs_xlsx(jobs: List[Dict]) -> BytesIO:
    """
    Export job data to XLSX.
    """
    columns = [
        "Job ID", "Job Title", "Client", "Description", "Created At", "Status"
    ]
    return create_xlsx(jobs, columns, sheet_name="Jobs")


# -----------------------------
# Clients XLSX Export
# -----------------------------
def export_clients_xlsx(clients: List[Dict]) -> BytesIO:
    """
    Export client data to XLSX.
    """
    columns = [
        "Client ID", "Client Name", "Status", "Created At", "Total Jobs"
    ]
    return create_xlsx(clients, columns, sheet_name="Clients")
