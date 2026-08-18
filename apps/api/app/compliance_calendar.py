"""
Phase 11 (partial): Statutory Compliance Calendar (Section 77).

Due-date rules below are genuine, standard Indian statutory due dates as of
this system's knowledge cutoff — not invented. Each is commented with what
it is. Firms should treat this as a starting default (and the versioned rule
engine from Phase 2 is where these belong long-term, per every prior phase's
same caveat), not as a substitute for checking current notifications — due
dates do change via government notification, and this system has no live
regulatory-change feed (Section 91) to catch that automatically.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import calendar


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass
class CalendarRule:
    statutory_type: str
    filing_or_payment: str
    due_day: int
    months_after: int  # 0 = same month as the period, 1 = following month


# Genuine standard due dates:
# - GSTR-3B: 20th of the following month (for most taxpayers; some states/
#   turnover bands have staggered 22nd/24th dates not modeled here)
# - GSTR-1: 11th of the following month (monthly filers)
# - TDS payment: 7th of the following month (30 April for March)
# - PF (ECR + payment): 15th of the following month
# - ESI: 15th of the following month
# - Professional Tax: typically 15th/20th of the following month (varies by
#   state — 15th used here as a common default, NOT authoritative for every
#   state)
CALENDAR_RULES = [
    CalendarRule("GST", "GSTR-3B", 20, 1),
    CalendarRule("GST", "GSTR-1", 11, 1),
    CalendarRule("TDS", "TDS Payment", 7, 1),
    CalendarRule("PF", "PF ECR + Payment", 15, 1),
    CalendarRule("ESI", "ESI Payment", 15, 1),
    CalendarRule("PT", "Professional Tax Payment", 15, 1),
]


@dataclass
class GeneratedCalendarItem:
    statutory_type: str
    filing_or_payment: str
    period: str
    due_date: date


def generate_calendar_items(financial_year_start: date, financial_year_end: date) -> list[GeneratedCalendarItem]:
    """One item per rule per month within the FY. TDS's March liability is
    due 30 April (a fixed date, not the 7th) — the one genuine exception to
    the flat day-of-month rule, handled explicitly rather than silently
    producing a wrong date for year-end TDS."""
    items = []
    month_start = financial_year_start.replace(day=1)
    while month_start <= financial_year_end:
        period_label = month_start.strftime("%b-%Y")
        for rule in CALENDAR_RULES:
            if rule.statutory_type == "TDS" and month_start.month == 3:
                due = date(month_start.year, 4, 30)  # March TDS is due 30 April, not 7 April
            else:
                due_month = _add_months(month_start, rule.months_after)
                last_day = calendar.monthrange(due_month.year, due_month.month)[1]
                due = date(due_month.year, due_month.month, min(rule.due_day, last_day))
            items.append(GeneratedCalendarItem(rule.statutory_type, rule.filing_or_payment, period_label, due))
        month_start = _add_months(month_start, 1)
    return items


@dataclass
class CalendarStatus:
    status: str  # 'PENDING' | 'FILED_ON_TIME' | 'FILED_LATE' | 'OVERDUE'
    delay_days: int | None


def compute_status(due_date: date, actual_date: date | None, today: date) -> CalendarStatus:
    if actual_date is not None:
        delay = (actual_date - due_date).days
        return CalendarStatus("FILED_ON_TIME" if delay <= 0 else "FILED_LATE", delay)
    if today > due_date:
        return CalendarStatus("OVERDUE", (today - due_date).days)
    return CalendarStatus("PENDING", None)
