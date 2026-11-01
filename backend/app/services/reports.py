from __future__ import annotations

from collections import defaultdict
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from sqlalchemy.orm import Session

from app.models import Transaction

TRANSFER_CATEGORY = "Transfers (Self / Family)"


def monthly_summaries(db: Session, user_id: int) -> list[dict]:
    txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    buckets: dict[str, dict] = {}
    for txn in txns:
        month = txn.txn_date.strftime("%Y-%m")
        bucket = buckets.setdefault(
            month,
            {
                "month": month,
                "total_debit": 0.0,
                "total_credit": 0.0,
                "transfer_out": 0.0,
                "by_category": defaultdict(float),
                "transaction_count": 0,
            },
        )
        bucket["transaction_count"] += 1
        if txn.direction == "credit":
            bucket["total_credit"] += txn.amount
        elif txn.category == TRANSFER_CATEGORY:
            bucket["transfer_out"] += txn.amount
        else:
            bucket["total_debit"] += txn.amount
            bucket["by_category"][txn.category] += txn.amount

    rows = []
    for month in sorted(buckets):
        item = buckets[month]
        item["by_category"] = dict(item["by_category"])
        for key in ("total_debit", "total_credit", "transfer_out"):
            item[key] = round(item[key], 2)
        rows.append(item)
    return rows


def dashboard_stats(db: Session, user_id: int) -> dict:
    summaries = monthly_summaries(db, user_id)
    latest = summaries[-1] if summaries else None
    return {
        "months": summaries,
        "latest": latest,
        "total_transactions": db.query(Transaction).filter(Transaction.user_id == user_id).count(),
    }


def excel_report(db: Session, user_id: int) -> bytes:
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.txn_date.asc())
        .all()
    )
    return _build_excel_report(txns)


def _build_excel_report(txns) -> bytes:
    wb = Workbook()
    overview = wb.active
    overview.title = "Overview"
    transactions = wb.create_sheet("Transactions")
    monthly = wb.create_sheet("Monthly Trends")
    categories = wb.create_sheet("Categories")

    navy = "0F172A"
    slate = "334155"
    muted = "64748B"
    cyan = "0EA5E9"
    cyan_light = "E0F2FE"
    green = "10B981"
    green_light = "D1FAE5"
    amber = "F59E0B"
    amber_light = "FEF3C7"
    white = "FFFFFF"
    soft = "F8FAFC"
    line = "E2E8F0"
    thin = Side(style="thin", color=line)

    debit_txns = [t for t in txns if t.direction != "credit" and t.category != TRANSFER_CATEGORY]
    credit_txns = [t for t in txns if t.direction == "credit"]
    transfer_txns = [t for t in txns if t.direction != "credit" and t.category == TRANSFER_CATEGORY]
    total_spent = round(sum(t.amount for t in debit_txns), 2)
    total_credited = round(sum(t.amount for t in credit_txns), 2)
    transfer_out = round(sum(t.amount for t in transfer_txns), 2)

    monthly_map = defaultdict(lambda: {"spent": 0.0, "credited": 0.0, "transfers": 0.0, "count": 0})
    category_map = defaultdict(lambda: {"amount": 0.0, "count": 0})
    merchant_map = defaultdict(float)
    for t in txns:
        month_key = t.txn_date.strftime("%Y-%m")
        monthly_map[month_key]["count"] += 1
        if t.direction == "credit":
            monthly_map[month_key]["credited"] += t.amount
        elif t.category == TRANSFER_CATEGORY:
            monthly_map[month_key]["transfers"] += t.amount
        else:
            monthly_map[month_key]["spent"] += t.amount
            category_map[t.category]["amount"] += t.amount
            category_map[t.category]["count"] += 1
            merchant_map[t.merchant or "Unknown"] += t.amount

    overview.merge_cells("A1:H2")
    overview["A1"] = "SpendSense - Spending Report"
    overview["A1"].font = Font(size=22, bold=True, color=white)
    overview["A1"].fill = PatternFill("solid", fgColor=navy)
    overview["A1"].alignment = Alignment(vertical="center")
    overview.row_dimensions[1].height = 28
    overview.row_dimensions[2].height = 10
    overview.merge_cells("A3:H3")
    overview["A3"] = "Summary-first report. Spending excludes self/family transfers; GPay UPI Lite top-ups are not imported as expenses."
    overview["A3"].font = Font(size=10, color=muted, italic=True)

    cards = [
        ("A5:B7", "Total spent", total_spent, cyan_light, cyan),
        ("C5:D7", "Money credited", total_credited, green_light, green),
        ("E5:F7", "Transfers out", transfer_out, amber_light, amber),
        ("G5:H7", "Transactions", len(txns), "F1F5F9", slate),
    ]
    for cell_range, label, value, fill_color, accent in cards:
        overview.merge_cells(cell_range)
        cell = overview[cell_range.split(":")[0]]
        is_count = label == "Transactions"
        cell.value = f"{label}\n{int(value) if is_count else '₹' + format(value, ',.2f')}"
        cell.font = Font(size=12, bold=True, color=slate)
        cell.fill = PatternFill("solid", fgColor=fill_color)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = Border(left=Side(style="medium", color=accent), top=thin, right=thin, bottom=thin)

    overview["A10"] = "Monthly cash flow"
    overview["A10"].font = Font(size=14, bold=True, color=navy)
    monthly_headers = ["Month", "Spent", "Credited", "Net cash flow", "Transfers", "Transactions"]
    for col, value in enumerate(monthly_headers, 1):
        c = overview.cell(row=11, column=col, value=value)
        c.font = Font(bold=True, color=white)
        c.fill = PatternFill("solid", fgColor=slate)
        c.alignment = Alignment(horizontal="center")
    months = sorted(monthly_map)
    for r, month_key in enumerate(months, 12):
        item = monthly_map[month_key]
        vals = [
            month_key,
            round(item["spent"], 2),
            round(item["credited"], 2),
            round(item["credited"] - item["spent"], 2),
            round(item["transfers"], 2),
            item["count"],
        ]
        for cidx, value in enumerate(vals, 1):
            cell = overview.cell(row=r, column=cidx, value=value)
            cell.fill = PatternFill("solid", fgColor=white if r % 2 == 0 else soft)
            cell.border = Border(bottom=thin)
            if cidx in (2, 3, 4, 5):
                cell.number_format = '₹#,##0.00;[Red]-₹#,##0.00'

    category_rows = sorted(category_map.items(), key=lambda item: item[1]["amount"], reverse=True)
    overview["H10"] = "Top categories"
    overview["H10"].font = Font(size=14, bold=True, color=navy)
    for col, value in enumerate(["Category", "Spent", "Share"], 8):
        c = overview.cell(row=11, column=col, value=value)
        c.font = Font(bold=True, color=white)
        c.fill = PatternFill("solid", fgColor=slate)
    for r, (cat, info) in enumerate(category_rows[:8], 12):
        overview.cell(r, 8, cat)
        overview.cell(r, 9, round(info["amount"], 2)).number_format = '₹#,##0.00'
        overview.cell(r, 10, (info["amount"] / total_spent) if total_spent else 0).number_format = "0.0%"

    top_merchants = sorted(merchant_map.items(), key=lambda item: item[1], reverse=True)[:8]
    overview["L10"] = "Top merchants"
    overview["L10"].font = Font(size=14, bold=True, color=navy)
    for col, value in enumerate(["Merchant", "Spent"], 12):
        c = overview.cell(row=11, column=col, value=value)
        c.font = Font(bold=True, color=white)
        c.fill = PatternFill("solid", fgColor=slate)
    for r, (merchant, amount) in enumerate(top_merchants, 12):
        overview.cell(r, 12, merchant)
        overview.cell(r, 13, round(amount, 2)).number_format = '₹#,##0.00'

    if months:
        chart = LineChart()
        chart.title = "Monthly spend vs credits"
        chart.y_axis.title = "Amount (₹)"
        chart.x_axis.title = "Month"
        data = Reference(overview, min_col=2, max_col=3, min_row=11, max_row=11 + len(months))
        cats = Reference(overview, min_col=1, min_row=12, max_row=11 + len(months))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.height = 7.5
        chart.width = 13
        chart.style = 10
        overview.add_chart(chart, "A21")

    if category_rows:
        chart2 = BarChart()
        chart2.type = "bar"
        chart2.title = "Top spending categories"
        chart2.height = 7.5
        chart2.width = 10
        data = Reference(overview, min_col=9, min_row=11, max_row=11 + min(8, len(category_rows)))
        cats = Reference(overview, min_col=8, min_row=12, max_row=11 + min(8, len(category_rows)))
        chart2.add_data(data, titles_from_data=True)
        chart2.set_categories(cats)
        chart2.legend = None
        chart2.style = 10
        overview.add_chart(chart2, "H21")

    overview.freeze_panes = "A11"
    overview.sheet_view.showGridLines = False
    for col, width in {"A":14,"B":15,"C":15,"D":17,"E":15,"F":14,"G":3,"H":24,"I":15,"J":12,"K":3,"L":28,"M":15}.items():
        overview.column_dimensions[col].width = width

    txn_headers = ["Date", "Merchant", "Category", "Amount", "Direction", "Source", "Description", "Recurring"]
    transactions.append(txn_headers)
    for t in sorted(txns, key=lambda x: x.txn_date, reverse=True):
        transactions.append([
            t.txn_date.date(),
            t.merchant,
            t.category,
            round(t.amount, 2),
            t.direction.title(),
            t.source.replace("_", " ").title(),
            t.cleaned_description or t.raw_description,
            "Yes" if getattr(t, "is_recurring", False) else "No",
        ])
    _style_data_sheet(transactions, "TransactionsTable", navy, soft, line, white)
    transactions.freeze_panes = "A2"
    transactions.auto_filter.ref = transactions.dimensions
    transactions.column_dimensions["A"].width = 13
    transactions.column_dimensions["B"].width = 28
    transactions.column_dimensions["C"].width = 24
    transactions.column_dimensions["D"].width = 14
    transactions.column_dimensions["E"].width = 12
    transactions.column_dimensions["F"].width = 16
    transactions.column_dimensions["G"].width = 48
    transactions.column_dimensions["H"].width = 12
    for cell in transactions["D"][1:]:
        cell.number_format = '₹#,##0.00'
    for cell in transactions["A"][1:]:
        cell.number_format = "dd-mmm-yyyy"

    monthly.append(monthly_headers)
    for month_key in months:
        item = monthly_map[month_key]
        monthly.append([
            month_key,
            round(item["spent"], 2),
            round(item["credited"], 2),
            round(item["credited"] - item["spent"], 2),
            round(item["transfers"], 2),
            item["count"],
        ])
    _style_data_sheet(monthly, "MonthlyTable", navy, soft, line, white)
    monthly.freeze_panes = "A2"
    for col in "BCDE":
        for cell in monthly[col][1:]:
            cell.number_format = '₹#,##0.00;[Red]-₹#,##0.00'
    for col, width in {"A":14,"B":16,"C":16,"D":18,"E":16,"F":14}.items():
        monthly.column_dimensions[col].width = width

    categories.append(["Category", "Spent", "Share of spend", "Transactions"])
    for cat, info in category_rows:
        categories.append([
            cat,
            round(info["amount"], 2),
            (info["amount"] / total_spent) if total_spent else 0,
            info["count"],
        ])
    _style_data_sheet(categories, "CategoriesTable", navy, soft, line, white)
    categories.freeze_panes = "A2"
    categories.column_dimensions["A"].width = 28
    categories.column_dimensions["B"].width = 16
    categories.column_dimensions["C"].width = 16
    categories.column_dimensions["D"].width = 15
    for cell in categories["B"][1:]:
        cell.number_format = '₹#,##0.00'
    for cell in categories["C"][1:]:
        cell.number_format = "0.0%"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _style_data_sheet(ws, table_name: str, header_color: str, alt_color: str, line_color: str, white: str) -> None:
    ws.sheet_view.showGridLines = False
    for cell in ws[1]:
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=header_color)
        cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 24
    for row in range(2, ws.max_row + 1):
        if row % 2:
            for cell in ws[row]:
                cell.fill = PatternFill("solid", fgColor=alt_color)
        for cell in ws[row]:
            cell.border = Border(bottom=Side(style="hair", color=line_color))
            cell.alignment = Alignment(vertical="top", wrap_text=False)
    if ws.max_row >= 2 and ws.max_column >= 1:
        ref = f"A1:{ws.cell(ws.max_row, ws.max_column).coordinate}"
        table = Table(displayName=table_name, ref=ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        ws.add_table(table)
