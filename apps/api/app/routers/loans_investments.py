from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..loans import check_loan, check_interest_consistency, reconcile_loans_to_gl
from ..investments import assess_investment, reconcile_investments_to_gl

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["loans-investments"])


class LoanRowOut(BaseModel):
    lender_or_borrower: str
    direction: str
    outstanding_balance: float
    maturity_date: str | None
    default_flag: str | None
    interest_flag: str | None


class LoanSummaryOut(BaseModel):
    loans: list[LoanRowOut]
    borrowings_total: float
    gl_borrowings_balance: float | None
    reconciliation_status: str
    reconciliation_difference: float
    overdue_count: int


@router.get("/loans", response_model=LoanSummaryOut)
async def get_loans(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        rows = await conn.fetch(
            "select lender_or_borrower, direction, principal_amount, interest_rate, maturity_date, outstanding_balance from loan where engagement_id=$1",
            engagement_id,
        )
        gl_borrowings = await conn.fetchval(
            """select sum(t.credit - t.debit) from trial_balance_line t join account a on a.id=t.account_id
               where t.engagement_id=$1 and a.note_ref='Borrowings'""",
            engagement_id,
        )
        finance_cost_total = await conn.fetchval(
            """select sum(t.debit - t.credit) from trial_balance_line t join account a on a.id=t.account_id
               where t.engagement_id=$1 and a.note_ref='Finance Costs'""",
            engagement_id,
        )

    out_rows = []
    for r in rows:
        loan_dict = {
            "lender_or_borrower": r["lender_or_borrower"], "direction": r["direction"],
            "outstanding_balance": float(r["outstanding_balance"]), "maturity_date": r["maturity_date"],
            "interest_rate": float(r["interest_rate"]) if r["interest_rate"] is not None else None,
            "principal_amount": float(r["principal_amount"]),
        }
        default_check = check_loan(loan_dict, eng["reporting_date"])
        interest_check = check_interest_consistency(loan_dict, float(finance_cost_total) if finance_cost_total else None)
        out_rows.append(LoanRowOut(
            lender_or_borrower=r["lender_or_borrower"], direction=r["direction"],
            outstanding_balance=float(r["outstanding_balance"]),
            maturity_date=str(r["maturity_date"]) if r["maturity_date"] else None,
            default_flag=default_check.flag, interest_flag=interest_check.flag,
        ))

    borrowings_total = sum(r.outstanding_balance for r in out_rows if r.direction == "BORROWING")
    recon = reconcile_loans_to_gl(borrowings_total, float(gl_borrowings) if gl_borrowings is not None else None)

    return LoanSummaryOut(
        loans=out_rows, borrowings_total=borrowings_total,
        gl_borrowings_balance=recon.gl_total if recon.status != "NO_DATA" else None,
        reconciliation_status=recon.status, reconciliation_difference=recon.difference,
        overdue_count=sum(1 for r in out_rows if r.default_flag),
    )


class InvestmentRowOut(BaseModel):
    investee_name: str
    cost: float
    fair_value: float | None
    unrealized_gain_loss: float | None
    flags: list[str]


class InvestmentSummaryOut(BaseModel):
    investments: list[InvestmentRowOut]
    cost_total: float
    gl_investments_balance: float | None
    reconciliation_status: str
    reconciliation_difference: float
    flagged_count: int


@router.get("/investments", response_model=InvestmentSummaryOut)
async def get_investments(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        rows = await conn.fetch(
            "select investee_name, cost, fair_value, fair_value_date, classification from investment where engagement_id=$1",
            engagement_id,
        )
        gl_inv = await conn.fetchval(
            """select sum(t.debit - t.credit) from trial_balance_line t join account a on a.id=t.account_id
               where t.engagement_id=$1 and a.note_ref='Investments'""",
            engagement_id,
        )

    out_rows = []
    for r in rows:
        inv_dict = {
            "investee_name": r["investee_name"], "cost": float(r["cost"]),
            "fair_value": float(r["fair_value"]) if r["fair_value"] is not None else None,
            "fair_value_date": r["fair_value_date"], "classification": r["classification"],
        }
        a = assess_investment(inv_dict, eng["reporting_date"])
        out_rows.append(InvestmentRowOut(
            investee_name=a.investee_name, cost=a.cost, fair_value=a.fair_value,
            unrealized_gain_loss=a.unrealized_gain_loss, flags=a.flags,
        ))

    cost_total = sum(r.cost for r in out_rows)
    recon = reconcile_investments_to_gl(cost_total, float(gl_inv) if gl_inv is not None else None)

    return InvestmentSummaryOut(
        investments=out_rows, cost_total=cost_total,
        gl_investments_balance=recon.gl_total if recon.status != "NO_DATA" else None,
        reconciliation_status=recon.status, reconciliation_difference=recon.difference,
        flagged_count=sum(1 for r in out_rows if r.flags),
    )
