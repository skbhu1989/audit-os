"""
Pre-Audit Module: Books Health Score (Section 58).

Same honesty principle as Phase 7's risk engine: the score is built only
from signals this system actually computes (TB balance-direction flags,
suspense accounts, unmapped accounts, HIGH/CRITICAL journal risk) — not a
comprehensive "books quality" assessment, and the factors list says exactly
what went into it.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class BooksHealthResult:
    score: float  # 0-100, 100 = healthiest
    factors: list[str] = field(default_factory=list)


def compute_books_health(
    suspense_account_count: int,
    tb_flag_count: int,
    unmapped_account_count: int,
    total_account_count: int,
    high_critical_je_count: int,
    total_je_count: int,
) -> BooksHealthResult:
    penalty = 0.0
    factors = []

    if suspense_account_count > 0:
        penalty += min(20, suspense_account_count * 10)
        factors.append(f"{suspense_account_count} suspense account(s) with a non-zero balance")

    if tb_flag_count > 0:
        penalty += min(25, tb_flag_count * 8)
        factors.append(f"{tb_flag_count} account(s) with an unexpected balance direction")

    if total_account_count > 0:
        unmapped_pct = unmapped_account_count / total_account_count
        if unmapped_pct > 0:
            penalty += min(25, unmapped_pct * 50)
            factors.append(f"{unmapped_account_count} of {total_account_count} accounts not yet approved to a financial statement line ({unmapped_pct*100:.0f}%)")

    if total_je_count > 0:
        hc_pct = high_critical_je_count / total_je_count
        if hc_pct > 0:
            penalty += min(30, hc_pct * 100)
            factors.append(f"{high_critical_je_count} of {total_je_count} journal entries scored HIGH/CRITICAL risk ({hc_pct*100:.0f}%)")

    score = round(max(0.0, 100.0 - penalty), 1)
    if not factors:
        factors = ["No suspense balances, balance-direction anomalies, unmapped accounts, or high-risk journals identified"]

    return BooksHealthResult(score, factors)
