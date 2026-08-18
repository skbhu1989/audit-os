"""
Reconciliation numeric-accuracy regression tests.

Every other test in this suite checks that endpoints behave correctly
(status codes, persistence, security). This file checks something
different and arguably more important for an audit system: that the
actual FINANCIAL ARITHMETIC is correct — a reconciliation engine that
returns 200 OK with a silently wrong difference amount would pass every
other test in this suite while still being useless (or actively
misleading) for its actual purpose.
"""
import io
from .conftest import auth_headers

SALES_REGISTER = """Invoice No,Date,Customer Name,GSTIN,Taxable Value,CGST,SGST,IGST,Total
INV-9001,05/04/2025,Test Customer Ltd,27AAACT1234A1Z5,1000000,90000,90000,0,1180000
"""

# Deliberately understated by exactly Rs 20,000 vs the books figure above —
# a known, hand-computed difference to assert against exactly.
GSTR1_WITH_KNOWN_MISMATCH = """Invoice No,Date,Customer Name,GSTIN,Taxable Value,CGST,SGST,IGST,Total
INV-9001,05/04/2025,Test Customer Ltd,27AAACT1234A1Z5,980000,90000,90000,0,1160000
"""


def _csv(name, content):
    return (name, io.BytesIO(content.encode()), "text/csv")


def test_gst_reconciliation_computes_exact_difference(client, engagement_a):
    headers = auth_headers(engagement_a)
    eng_id = engagement_a["engagement_id"]

    sales = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "SALES_REGISTER", "on_duplicate": "ASK"},
        files={"file": _csv("sales.csv", SALES_REGISTER)},
    )
    assert sales.status_code == 201 and sales.json()["status"] == "COMPLETED", sales.text

    gstr1 = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "GSTR1", "on_duplicate": "ASK"},
        files={"file": _csv("gstr1.csv", GSTR1_WITH_KNOWN_MISMATCH)},
    )
    assert gstr1.status_code == 201 and gstr1.json()["status"] == "COMPLETED", gstr1.text

    run = client.post(f"/engagements/{eng_id}/analytics/gst-reconciliation/run", headers=headers)
    assert run.status_code == 200, run.text
    summary = run.json()
    assert summary["books_vs_gstr1"]["total"] == 1
    assert summary["books_vs_gstr1"]["partial"] == 1, "A same-invoice amount mismatch must be PARTIALLY_MATCHED, not silently MATCHED or UNMATCHED"

    exceptions = client.get(f"/engagements/{eng_id}/gst-reconciliation", headers=headers)
    assert exceptions.status_code == 200
    matches = [e for e in exceptions.json() if e["document_no"] == "INV-9001"]
    assert len(matches) == 1
    # The exact hand-computed figure: books total 1,180,000 minus return
    # total 1,160,000 = 20,000 — not "some difference," the precise one.
    assert abs(matches[0]["difference"] - 20000.0) < 0.01, (
        f"Expected an exact Rs 20,000 difference, got {matches[0]['difference']}"
    )


TDS_LEDGER = """Section,Deductee Name,PAN,Amount Paid Credited,TDS Amount,Deduction Date
194J,Test Professional,AAACT1234A,4150000,415000,15/04/2025
"""

# Short-paid by exactly Rs 15,000 vs the ledger figure above.
TDS_CHALLAN_SHORT_PAID = """Section,Challan No,BSR Code,Challan Date,Amount
194J,CH-9001,0123456,10/05/2025,400000
"""


def test_tds_interest_calculation_is_exact(client, engagement_a):
    """Regression test for the exact formula: 1.5%/month x shortfall x
    months_overdue. A wrong interest figure here would be a real audit
    finding presented to a client with a wrong number attached."""
    headers = auth_headers(engagement_a)
    eng_id = engagement_a["engagement_id"]

    ledger = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "TDS_LEDGER", "on_duplicate": "ASK"},
        files={"file": _csv("tds_ledger.csv", TDS_LEDGER)},
    )
    assert ledger.status_code == 201 and ledger.json()["status"] == "COMPLETED", ledger.text

    challan = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "TDS_CHALLAN", "on_duplicate": "ASK"},
        files={"file": _csv("tds_challan.csv", TDS_CHALLAN_SHORT_PAID)},
    )
    assert challan.status_code == 201 and challan.json()["status"] == "COMPLETED", challan.text

    run = client.post(f"/engagements/{eng_id}/analytics/tds-reconciliation/run", headers=headers)
    assert run.status_code == 200, run.text
    result = run.json()
    assert result["exceptions_found"] == 1

    # Shortfall = 415,000 - 400,000 = 15,000. The engine's default
    # months_overdue is 1 when not otherwise specified. Expected interest =
    # 15,000 * 0.015 * 1 = 225.00 exactly.
    assert abs(result["total_interest_exposure"] - 225.0) < 0.01, (
        f"Expected exactly Rs 225.00 interest (15,000 shortfall x 1.5% x 1 month), got {result['total_interest_exposure']}"
    )
