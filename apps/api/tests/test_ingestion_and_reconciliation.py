"""
Data ingestion + reconciliation regression tests.

Each test here maps to a specific real bug found during development:
- test_non_tying_trial_balance_is_not_persisted: Phase 4's bug where a
  dataset-level error (TB doesn't tie) would silently persist individually-
  valid-looking rows anyway.
- test_duplicate_upload_is_detected: the Pre-Audit Module incident where
  re-uploading a file with no duplicate detection silently doubled every
  row in a real engagement.
- test_payroll_reconciliation_handles_standard_payment_timing: Phase 11's
  false-positive bug where a completely normal, fully-paid PF/ESI liability
  (paid the following month, per standard practice) was flagged as two
  separate exceptions because the reconciliation compared same-calendar-
  month labels with no adjustment.
"""
import io
from .conftest import auth_headers


def _csv_file(name: str, content: str):
    return (name, io.BytesIO(content.encode()), "text/csv")


TB_TYING = """Ledger Name,Debit,Credit
Share Capital,,1000000
Trade Receivables,600000,
Cash & Bank Balances,400000,
"""

TB_NOT_TYING = """Ledger Name,Debit,Credit
Share Capital,,1000000
Trade Receivables,600000,
Cash & Bank Balances,100000,
"""


def test_tying_trial_balance_is_accepted_and_persisted(client, engagement_a):
    res = client.post(
        f"/engagements/{engagement_a['engagement_id']}/data/upload",
        headers=auth_headers(engagement_a),
        data={"dataset_type": "TRIAL_BALANCE", "on_duplicate": "ASK"},
        files={"file": _csv_file("tb.csv", TB_TYING)},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["rows_valid"] == 3

    tb = client.get(f"/engagements/{engagement_a['engagement_id']}/data/trial-balance", headers=auth_headers(engagement_a))
    assert tb.status_code == 200
    assert len(tb.json()) == 3


def test_non_tying_trial_balance_is_not_persisted(client, engagement_a):
    """Regression test for a real bug: a TB that doesn't tie is a
    dataset-level error, not a row-level one — none of its rows should be
    written, even though each individual row looks valid in isolation."""
    res = client.post(
        f"/engagements/{engagement_a['engagement_id']}/data/upload",
        headers=auth_headers(engagement_a),
        data={"dataset_type": "TRIAL_BALANCE", "on_duplicate": "ASK"},
        files={"file": _csv_file("tb_broken.csv", TB_NOT_TYING)},
    )
    assert res.status_code == 201
    assert res.json()["status"] == "FAILED"

    tb = client.get(f"/engagements/{engagement_a['engagement_id']}/data/trial-balance", headers=auth_headers(engagement_a))
    assert tb.status_code == 200
    assert tb.json() == [], "A non-tying trial balance must not persist ANY rows"


def test_duplicate_upload_is_detected_not_silently_reingested(client, engagement_a):
    """Regression test for the real Pre-Audit Module data-corruption
    incident: re-uploading the exact same file must be detected, not
    silently double-ingested."""
    headers = auth_headers(engagement_a)
    eng_id = engagement_a["engagement_id"]

    first = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "TRIAL_BALANCE", "on_duplicate": "ASK"},
        files={"file": _csv_file("tb.csv", TB_TYING)},
    )
    assert first.status_code == 201
    assert first.json()["status"] == "COMPLETED"

    second = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "TRIAL_BALANCE", "on_duplicate": "ASK"},
        files={"file": _csv_file("tb.csv", TB_TYING)},
    )
    assert second.status_code == 201
    assert second.json().get("duplicate_detected") is True, "An identical re-upload must be flagged, not silently reingested"

    tb = client.get(f"/engagements/{eng_id}/data/trial-balance", headers=headers)
    assert len(tb.json()) == 3, "Row count must NOT double after the duplicate was correctly rejected"


PAYROLL_REGISTER = """Employee Code,Period,Gross Salary,PF Employee,PF Employer,ESI Employee,ESI Employer,PT Amount
E001,Apr-2025,50000,6000,6000,375,1750,200
"""

# PF challan paid in May for April's liability — the standard, correct
# timing (PF is due by the 15th of the following month). This must NOT
# be flagged as an exception.
PF_CHALLAN_ON_TIME = """Section,Challan No,BSR Code,Challan Date,Amount
PF,TRRN001,0123456,10/05/2025,12000
"""


def test_payroll_reconciliation_handles_standard_payment_timing(client, engagement_a):
    """Regression test for a real false-positive bug: PF paid the month
    after the liability accrued (standard practice) was previously flagged
    as TWO separate exceptions instead of correctly recognized as fully paid."""
    headers = auth_headers(engagement_a)
    eng_id = engagement_a["engagement_id"]

    r1 = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "PAYROLL_REGISTER", "on_duplicate": "ASK"},
        files={"file": _csv_file("payroll.csv", PAYROLL_REGISTER)},
    )
    assert r1.status_code == 201 and r1.json()["status"] == "COMPLETED"

    r2 = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "PF_CHALLAN", "on_duplicate": "ASK"},
        files={"file": _csv_file("pf.csv", PF_CHALLAN_ON_TIME)},
    )
    assert r2.status_code == 201 and r2.json()["status"] == "COMPLETED"

    run = client.post(f"/engagements/{eng_id}/analytics/payroll-reconciliation/run", headers=headers)
    assert run.status_code == 200
    pf_result = next(r for r in run.json() if r["scheme"] == "PF")
    assert pf_result["exceptions_found"] == 0, (
        "A fully-paid PF liability paid on standard timing (following month) must show zero exceptions"
    )
