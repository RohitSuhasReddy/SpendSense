from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from sqlalchemy.orm import Session

from app.models import Transaction

TRANSFER_CATEGORY = "Transfers (Self / Family)"


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + (value.month - 1) + months
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)


def _period_bounds(
    period: str,
    selected_month: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[datetime, datetime, str]:
    today = date.today()
    this_month = date(today.year, today.month, 1)

    if period == "selected_month":
        if not selected_month:
            raise ValueError("selected_month is required")
        try:
            start_day = datetime.strptime(selected_month, "%Y-%m").date().replace(day=1)
        except ValueError as exc:
            raise ValueError("selected_month must be YYYY-MM") from exc
        end_day = _add_months(start_day, 1)
        label = start_day.strftime("%B %Y")
    elif period == "current_month":
        start_day = this_month
        end_day = _add_months(this_month, 1)
        label = this_month.strftime("%B %Y")
    elif period == "previous_month":
        start_day = _add_months(this_month, -1)
        end_day = this_month
        label = start_day.strftime("%B %Y")
    elif period == "last_6_months":
        start_day = _add_months(this_month, -5)
        end_day = _add_months(this_month, 1)
        label = f"{start_day.strftime('%b %Y')} - {today.strftime('%b %Y')}"
    elif period == "last_12_months":
        start_day = _add_months(this_month, -11)
        end_day = _add_months(this_month, 1)
        label = f"{start_day.strftime('%b %Y')} - {today.strftime('%b %Y')}"
    elif period == "custom":
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required for a custom range")
        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")
        start_day = start_date
        end_day = end_date + timedelta(days=1)
        label = f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}"
    else:
        raise ValueError("Unknown report period")

    return (
        datetime.combine(start_day, datetime.min.time()),
        datetime.combine(end_day, datetime.min.time()),
        label,
    )


def monthly_summaries(db: Session, user_id: int) -> list[dict]:
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.txn_date.asc())
        .all()
    )
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


def dashboard_stats(db: Session, user_id: int, month: str | None = None) -> dict:
    summaries = monthly_summaries(db, user_id)
    selected = None
    if month:
        selected = next((item for item in summaries if item["month"] == month), None)
    if selected is None and summaries:
        selected = summaries[-1]

    return {
        "months": summaries,
        "selected": selected,
        "latest": summaries[-1] if summaries else None,
        "available_months": [item["month"] for item in summaries],
        "total_transactions": selected["transaction_count"] if selected else 0,
        "all_time_transactions": db.query(Transaction).filter(Transaction.user_id == user_id).count(),
    }


def excel_report(
    db: Session,
    user_id: int,
    period: str = "current_month",
    selected_month: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[bytes, str]:
    start_dt, end_dt, label = _period_bounds(
        period,
        selected_month=selected_month,
        start_date=start_date,
        end_date=end_date,
    )
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.txn_date >= start_dt,
            Transaction.txn_date < end_dt,
        )
        .order_by(Transaction.txn_date.asc())
        .all()
    )
    content = _build_excel_report(txns, label)
    filename = f"spendsense-{start_dt.date().isoformat()}-to-{(end_dt.date() - timedelta(days=1)).isoformat()}.xlsx"
    return content, filename


def _build_excel_report(txns, period_label: str) -> bytes:
    wb = Workbook()
    overview = wb.active
    overview.title = "Overview"
    transactions = wb.create_sheet("Transactions")
    monthly = wb.create_sheet("Monthly Trends")
    categories = wb.create_sheet("Categories")

    navy = "1F2937"
    steel = "4C6478"
    steel_light = "E8EEF3"
    sage = "5E7D73"
    sage_light = "E7EFEC"
    sand = "8A7E6B"
    sand_light = "F1EEE9"
    white = "FFFFFF"
    soft = "F7F8FA"
    muted = "667085"
    line = "D9DEE5"
    danger = "A94442"
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

    for txn in txns:
        month_key = txn.txn_date.strftime("%Y-%m")
        monthly_map[month_key]["count"] += 1
        if txn.direction == "credit":
            monthly_map[month_key]["credited"] += txn.amount
        elif txn.category == TRANSFER_CATEGORY:
            monthly_map[month_key]["transfers"] += txn.amount
        else:
            monthly_map[month_key]["spent"] += txn.amount
            category_map[txn.category]["amount"] += txn.amount
            category_map[txn.category]["count"] += 1
            merchant_map[txn.merchant or "Unknown"] += txn.amount

    overview.merge_cells("A1:M2")
    overview["A1"] = "SpendSense - Spending Report"
    overview["A1"].font = Font(size=22, bold=True, color=white)
    overview["A1"].fill = PatternFill("solid", fgColor=navy)
    overview["A1"].alignment = Alignment(vertical="center")
    overview.row_dimensions[1].height = 28
    overview.row_dimensions[2].height = 10

    overview.merge_cells("A3:M3")
    overview["A3"] = f"Report period: {period_label}"
    overview["A3"].font = Font(size=10, color=muted, italic=True)

    cards = [
        ("A5:B7", "Spent", total_spent, steel_light, steel),
        ("C5:D7", "Credited", total_credited, sage_light, sage),
        ("E5:F7", "Transfers", transfer_out, sand_light, sand),
        ("G5:H7", "Transactions", len(txns), "EEF1F4", navy),
    ]
    for cell_range, label, value, fill_color, accent in cards:
        overview.merge_cells(cell_range)
        cell = overview[cell_range.split(":")[0]]
        is_count = label == "Transactions"
        cell.value = f"{label}\n{int(value) if is_count else '₹' + format(value, ',.2f')}"
        cell.font = Font(size=12, bold=True, color=navy)
        cell.fill = PatternFill("solid", fgColor=fill_color)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = Border(left=Side(style="medium", color=accent), top=thin, right=thin, bottom=thin)

    overview["A10"] = "Monthly summary"
    overview["A10"].font = Font(size=14, bold=True, color=navy)
    monthly_headers = ["Month", "Spent", "Credited", "Net cash flow", "Transfers", "Transactions"]
    for col, value in enumerate(monthly_headers, 1):
        cell = overview.cell(row=11, column=col, value=value)
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=steel)
        cell.alignment = Alignment(horizontal="center")

    months = sorted(monthly_map)
    for row_index, month_key in enumerate(months, 12):
        item = monthly_map[month_key]
        values = [
            month_key,
            round(item["spent"], 2),
            round(item["credited"], 2),
            round(item["credited"] - item["spent"], 2),
            round(item["transfers"], 2),
            item["count"],
        ]
        for col_index, value in enumerate(values, 1):
            cell = overview.cell(row=row_index, column=col_index, value=value)
            cell.fill = PatternFill("solid", fgColor=white if row_index % 2 == 0 else soft)
            cell.border = Border(bottom=thin)
            if col_index in (2, 3, 4, 5):
                cell.number_format = '₹#,##0.00;[Red]-₹#,##0.00'
            if col_index == 4 and isinstance(value, (int, float)) and value < 0:
                cell.font = Font(color=danger)

    category_rows = sorted(category_map.items(), key=lambda item: item[1]["amount"], reverse=True)
    overview["H10"] = "Top categories"
    overview["H10"].font = Font(size=14, bold=True, color=navy)
    for col, value in enumerate(["Category", "Spent", "Share"], 8):
        cell = overview.cell(row=11, column=col, value=value)
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=steel)

    for row_index, (category, info) in enumerate(category_rows[:8], 12):
        overview.cell(row_index, 8, category)
        overview.cell(row_index, 9, round(info["amount"], 2)).number_format = '₹#,##0.00'
        overview.cell(row_index, 10, (info["amount"] / total_spent) if total_spent else 0).number_format = "0.0%"

    top_merchants = sorted(merchant_map.items(), key=lambda item: item[1], reverse=True)[:8]
    overview["L10"] = "Top merchants"
    overview["L10"].font = Font(size=14, bold=True, color=navy)
    for col, value in enumerate(["Merchant", "Spent"], 12):
        cell = overview.cell(row=11, column=col, value=value)
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=steel)

    for row_index, (merchant, amount) in enumerate(top_merchants, 12):
        overview.cell(row_index, 12, merchant)
        overview.cell(row_index, 13, round(amount, 2)).number_format = '₹#,##0.00'

    if category_rows:
        chart_row = max(22, 14 + len(months))
        chart = BarChart()
        chart.type = "bar"
        chart.title = f"Top spending categories - {period_label}"
        chart.x_axis.title = "Spend (₹)"
        chart.y_axis.title = "Category"
        chart.height = 8.5
        chart.width = 18
        chart.legend = None
        chart.gapWidth = 45
        limit = min(8, len(category_rows))
        data = Reference(overview, min_col=9, min_row=11, max_row=11 + limit)
        category_ref = Reference(overview, min_col=8, min_row=12, max_row=11 + limit)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(category_ref)
        chart.dLbls = DataLabelList()
        chart.dLbls.showVal = True
        chart.dLbls.position = "outEnd"
        if chart.series:
            chart.series[0].graphicalProperties.solidFill = steel
            chart.series[0].graphicalProperties.line.solidFill = steel
        overview.add_chart(chart, f"A{chart_row}")

    overview.freeze_panes = "A11"
    overview.sheet_view.showGridLines = False
    for col, width in {
        "A": 14, "B": 15, "C": 15, "D": 17, "E": 15, "F": 14,
        "G": 3, "H": 24, "I": 15, "J": 12, "K": 3, "L": 30, "M": 15
    }.items():
        overview.column_dimensions[col].width = width

    txn_headers = ["Date", "Merchant", "Category", "Amount", "Direction", "Source", "Description", "Recurring"]
    transactions.append(txn_headers)
    for txn in sorted(txns, key=lambda item: item.txn_date, reverse=True):
        transactions.append([
            txn.txn_date.date(),
            txn.merchant,
            txn.category,
            round(txn.amount, 2),
            txn.direction.title(),
            txn.source.replace("_", " ").title(),
            txn.cleaned_description or txn.raw_description,
            "Yes" if getattr(txn, "is_recurring", False) else "No",
        ])
    _style_data_sheet(transactions, "TransactionsTable", navy, soft, line, white)
    transactions.freeze_panes = "A2"
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
    for col, width in {"A": 14, "B": 16, "C": 16, "D": 18, "E": 16, "F": 14}.items():
        monthly.column_dimensions[col].width = width

    categories.append(["Category", "Spent", "Share of spend", "Transactions"])
    for category, info in category_rows:
        categories.append([
            category,
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


def _style_data_sheet(
    ws,
    table_name: str,
    header_color: str,
    alt_color: str,
    line_color: str,
    white: str,
) -> None:
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
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)
