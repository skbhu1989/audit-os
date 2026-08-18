"""
Data ingestion: turns a messy Excel/CSV export (Tally, Zoho, SAP, or a plain
spreadsheet — real-world column names vary a lot) into validated rows ready
to write into the Universal Data Model.

Design: parsing and validation are pure functions over pandas DataFrames,
with no DB or FastAPI dependency, so they can be unit-tested directly and
reused by a future async worker (Section CJ: long-running jobs should not
block the request/response cycle — this module doesn't care how it's called).
"""
from __future__ import annotations
import re
import pandas as pd
from dataclasses import dataclass, field


def _clean_str(val) -> str | None:
    """Handles pandas' NaN-for-missing-cell representation correctly.
    NaN is truthy in Python (`NaN or "x"` evaluates to NaN, not "x"), so a
    naive `str(val or "").strip() or None` silently turns a missing cell
    into the literal string "nan" instead of None. Caught by unit testing
    the vendor-master parser against a file with a blank PAN cell.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s and s.lower() != "nan" else None


def _json_safe_row(row) -> dict:
    """Convert a pandas Series to a dict safe for json.dumps → Postgres jsonb.
    Pandas represents missing cells as NaN (a float); Python's json module
    happily serializes float('nan') as the literal token `NaN`, which is
    valid to json.dumps but NOT valid JSON per RFC 8259 — Postgres's jsonb
    correctly rejects it. Caught by testing a file with a blank cell.
    """
    out = {}
    for k, v in row.to_dict().items():
        if isinstance(v, float) and pd.isna(v):
            out[k] = None
        else:
            out[k] = v
    return out


# ---------- column normalization ----------

def _normalize_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


ALIASES = {
    "trial_balance": {
        "ledger_name": ["ledgername", "ledger", "particulars", "account", "accountname"],
        "debit": ["debit", "dr", "debitamount", "debitamt"],
        "credit": ["credit", "cr", "creditamount", "creditamt"],
    },
    "journal": {
        "journal_no": ["journalno", "voucherno", "vchno", "journalid"],
        "posted_date": ["date", "voucherdate", "posteddate", "entrydate"],
        "posted_by": ["postedby", "user", "enteredby", "createdby"],
        "narration": ["narration", "description", "particulars", "notes"],
        "debit_account": ["debitaccount", "draccount", "debitledger"],
        "credit_account": ["creditaccount", "craccount", "creditledger"],
        "amount": ["amount", "amt", "value"],
    },
    "vendor_master": {
        "name": ["vendorname", "name", "suppliername", "party"],
        "gstin": ["gstin", "gstno", "gstnumber"],
        "pan": ["pan", "panno", "pannumber"],
        "address": ["address", "addr"],
        "bank_account": ["bankaccount", "bankaccountnumber", "accountnumber", "bankacno"],
    },
    "customer_master": {
        "name": ["customername", "name", "clientname", "party"],
        "gstin": ["gstin", "gstno", "gstnumber"],
        "pan": ["pan", "panno", "pannumber"],
        "address": ["address", "addr"],
    },
    "invoice_register": {
        "invoice_no": ["invoiceno", "billno", "voucherno", "docno"],
        "invoice_date": ["date", "invoicedate", "billdate", "docdate"],
        "party_name": ["partyname", "customername", "vendorname", "party", "name"],
        "gstin": ["gstin", "partygstin"],
        "taxable_value": ["taxablevalue", "taxableamount", "basicamount", "assessablevalue"],
        "cgst": ["cgst", "cgstamount", "cgstamt"],
        "sgst": ["sgst", "sgstamount", "sgstamt"],
        "igst": ["igst", "igstamount", "igstamt"],
        "cess": ["cess", "cessamount"],
        "total_value": ["total", "totalvalue", "invoicevalue", "grandtotal", "netamount"],
    },
    "bank_statement": {
        "txn_date": ["date", "transactiondate", "valuedate", "txndate"],
        "description": ["description", "narration", "particulars", "remarks"],
        "debit": ["debit", "withdrawal", "dr", "debitamount"],
        "credit": ["credit", "deposit", "cr", "creditamount"],
        "balance": ["balance", "closingbalance", "runningbalance", "balanceamount"],
    },
    "gstr3b_summary": {
        "period": ["period", "taxperiod", "month"],
        "taxable_value": ["taxablevalue", "taxableamount", "turnover"],
        "cgst": ["cgst"], "sgst": ["sgst"], "igst": ["igst"], "cess": ["cess"],
    },
    "tds_ledger": {
        "section": ["section", "tdssection"],
        "deductee_name": ["deducteename", "partyname", "name"],
        "deductee_pan": ["pan", "deducteepan"],
        "amount_paid_credited": ["amountpaidcredited", "grossamount", "amount"],
        "tds_amount": ["tdsamount", "tds", "taxdeducted"],
        "deduction_date": ["deductiondate", "date"],
    },
    "tds_challan": {
        "section": ["section", "tdssection"],
        "challan_no": ["challanno", "cin"],
        "bsr_code": ["bsrcode", "bsr"],
        "challan_date": ["challandate", "date"],
        "amount": ["amount", "challanamount"],
    },
    "tds_return": {
        "section": ["section", "tdssection"],
        "deductee_pan": ["pan", "deducteepan"],
        "tds_amount": ["tdsamount", "tds", "taxdeducted"],
        "quarter": ["quarter", "qtr"],
    },
    "employee_master": {
        "employee_code": ["employeecode", "empcode", "code", "id"],
        "name": ["name", "employeename"],
        "pan": ["pan"],
        "uan": ["uan", "pfnumber"],
        "date_of_joining": ["dateofjoining", "doj", "joiningdate"],
    },
    "payroll_register": {
        "employee_code": ["employeecode", "empcode", "code"],
        "period": ["period", "month", "payperiod"],
        "gross_salary": ["grosssalary", "gross", "salary"],
        "pf_employee": ["pfemployee", "pfemployeeshare", "employeepf"],
        "pf_employer": ["pfemployer", "pfemployershare", "employerpf"],
        "esi_employee": ["esiemployee", "esiemployeeshare", "employeeesi"],
        "esi_employer": ["esiemployer", "esiemployershare", "employeresi"],
        "pt_amount": ["ptamount", "professionaltax", "pt"],
    },
    "fixed_asset_register": {
        "asset_code": ["assetcode", "assetid", "code"],
        "description": ["description", "assetdescription", "particulars"],
        "category": ["category", "assetcategory", "assetclass"],
        "acquisition_date": ["acquisitiondate", "purchasedate", "capitalisationdate", "capitalizationdate"],
        "gross_block": ["grossblock", "originalcost", "cost", "grossvalue"],
        "accum_depreciation": ["accumulateddepreciation", "accumdepreciation", "accumdep"],
        "useful_life_years": ["usefullifeyears", "usefullife", "life"],
        "depreciation_method": ["depreciationmethod", "method"],
        "disposal_date": ["disposaldate"],
        "disposal_proceeds": ["disposalproceeds", "saleproceeds"],
    },
    "inventory_register": {
        "item_code": ["itemcode", "code", "sku"],
        "description": ["description", "itemdescription", "particulars"],
        "quantity_on_hand": ["quantityonhand", "quantity", "qty", "closingstock"],
        "unit_cost": ["unitcost", "cost", "rate"],
        "nrv": ["nrv", "netrealisablevalue", "netrealizablevalue"],
        "ageing_days": ["ageingdays", "agedays", "age"],
    },
    "loan_register": {
        "lender_or_borrower": ["lenderorborrower", "lendername", "party", "bankname"],
        "direction": ["direction", "type", "loantype"],
        "principal_amount": ["principalamount", "principal", "sanctionamount", "loanamount"],
        "interest_rate": ["interestrate", "rate", "roi"],
        "start_date": ["startdate", "disbursementdate", "sanctiondate"],
        "maturity_date": ["maturitydate", "duedate", "repaymentdate"],
        "outstanding_balance": ["outstandingbalance", "outstanding", "balance", "closingbalance"],
    },
    "investment_register": {
        "investee_name": ["investeename", "name", "company", "fundname"],
        "investment_type": ["investmenttype", "type", "instrument"],
        "classification": ["classification", "category"],
        "cost": ["cost", "costofacquisition", "purchasevalue"],
        "fair_value": ["fairvalue", "marketvalue", "currentvalue", "nav"],
        "fair_value_date": ["fairvaluedate", "valuationdate", "navdate"],
    },
    "intercompany_ledger": {
        "counterparty_name": ["counterpartyname", "entity", "counterparty", "relatedparty"],
        "transaction_type": ["transactiontype", "type", "nature"],
        "transaction_date": ["transactiondate", "date"],
        "amount": ["amount", "value"],
        "currency": ["currency", "ccy"],
        "reference_no": ["referenceno", "reference", "invoiceno", "docno"],
    },
}


def normalize_columns(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    alias_map = ALIASES[dataset]
    lookup = {}
    for canonical, variants in alias_map.items():
        for v in variants:
            lookup[v] = canonical

    rename = {}
    for col in df.columns:
        key = _normalize_key(col)
        if key in lookup:
            rename[col] = lookup[key]
    df = df.rename(columns=rename)
    df.columns = [c if c in alias_map else _normalize_key(c) for c in df.columns]
    return df


# ---------- validation result plumbing ----------

@dataclass
class ValidationIssue:
    row_number: int
    field: str | None
    message: str
    severity: str  # 'WARNING' | 'ERROR'
    raw_row: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    valid_rows: list[dict]
    issues: list[ValidationIssue]
    rows_total: int

    @property
    def rows_valid(self) -> int:
        return len(self.valid_rows)

    @property
    def rows_rejected(self) -> int:
        return len({i.row_number for i in self.issues if i.severity == "ERROR"})

    def quality_score(self) -> float:
        if self.rows_total == 0:
            return 0.0
        error_rows = self.rows_rejected
        warning_rows = len({i.row_number for i in self.issues if i.severity == "WARNING"})
        # errors cost more than warnings; floor at 0
        penalty = (error_rows * 2 + warning_rows) / max(self.rows_total, 1)
        return round(max(0.0, 100.0 - penalty * 100.0), 2)


def load_tabular(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """dtype=str on load is deliberate: without it, pandas auto-infers numeric
    columns and silently strips leading zeros from anything that looks like a
    number — e.g. a BSR code '0123456' becomes 123456. That's fatal for
    matching against government records where the leading zero is part of the
    identifier. Every parser already explicitly converts genuinely-numeric
    fields (amounts, taxable values) via pd.to_numeric(), so forcing string
    dtype here only protects code-like fields; it doesn't break amount parsing.
    Caught by testing a real BSR code, not by reading the loader code.
    """
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(pd.io.common.BytesIO(file_bytes), dtype=str)
    return pd.read_csv(pd.io.common.BytesIO(file_bytes), dtype=str)


# ---------- Trial Balance ----------

def parse_trial_balance(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "trial_balance")
    issues: list[ValidationIssue] = []
    valid_rows = []
    seen_ledgers = set()

    required = {"ledger_name", "debit", "credit"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2  # +1 for 0-index, +1 for header row
        raw = _json_safe_row(row)
        ledger = str(row.get("ledger_name", "")).strip()
        debit = pd.to_numeric(row.get("debit"), errors="coerce")
        credit = pd.to_numeric(row.get("credit"), errors="coerce")

        if not ledger or ledger.lower() == "nan":
            issues.append(ValidationIssue(rn, "ledger_name", "Ledger name is missing", "ERROR", raw))
            continue
        if pd.isna(debit):
            debit = 0.0
        if pd.isna(credit):
            credit = 0.0
        if debit < 0 or credit < 0:
            issues.append(ValidationIssue(rn, "debit/credit", "Negative amount in a trial balance line", "ERROR", raw))
            continue
        if debit > 0 and credit > 0:
            issues.append(ValidationIssue(rn, "debit/credit", "Both debit and credit are non-zero on the same line", "ERROR", raw))
            continue
        if debit == 0 and credit == 0:
            issues.append(ValidationIssue(rn, "debit/credit", "Both debit and credit are zero", "WARNING", raw))

        key = ledger.lower()
        if key in seen_ledgers:
            issues.append(ValidationIssue(rn, "ledger_name", f"Duplicate ledger '{ledger}' — later occurrence will overwrite the earlier one", "WARNING", raw))
        seen_ledgers.add(key)

        valid_rows.append({"ledger_name": ledger, "debit": float(debit), "credit": float(credit)})

    total_dr = sum(r["debit"] for r in valid_rows)
    total_cr = sum(r["credit"] for r in valid_rows)
    if valid_rows and abs(total_dr - total_cr) > 1.0:  # tolerance for rounding
        issues.append(ValidationIssue(
            0, None,
            f"Trial balance does not tie: total debit {total_dr:,.2f} vs total credit {total_cr:,.2f} "
            f"(difference {total_dr - total_cr:,.2f})",
            "ERROR",
        ))

    return ParseResult(valid_rows, issues, len(df))


# ---------- Journal / General Ledger ----------

def parse_journal(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "journal")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"posted_date", "debit_account", "credit_account", "amount"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        date = pd.to_datetime(row.get("posted_date"), errors="coerce", dayfirst=True)
        amount = pd.to_numeric(row.get("amount"), errors="coerce")
        dr_acc = str(row.get("debit_account", "")).strip()
        cr_acc = str(row.get("credit_account", "")).strip()

        if pd.isna(date):
            issues.append(ValidationIssue(rn, "posted_date", f"Unparseable date: {row.get('posted_date')!r}", "ERROR", raw))
            continue
        if pd.isna(amount) or amount <= 0:
            issues.append(ValidationIssue(rn, "amount", "Amount is missing, zero, or negative", "ERROR", raw))
            continue
        if not dr_acc or not cr_acc or dr_acc.lower() == "nan" or cr_acc.lower() == "nan":
            issues.append(ValidationIssue(rn, "debit_account/credit_account", "Journal line is missing a debit or credit account — unbalanced entry", "ERROR", raw))
            continue
        if dr_acc == cr_acc:
            issues.append(ValidationIssue(rn, "debit_account/credit_account", f"Debit and credit account are the same ('{dr_acc}')", "WARNING", raw))

        valid_rows.append({
            "journal_no": _clean_str(row.get("journal_no")),
            "posted_date": date.date(),
            "posted_by": _clean_str(row.get("posted_by")),
            "narration": _clean_str(row.get("narration")),
            "debit_account": dr_acc,
            "credit_account": cr_acc,
            "amount": float(amount),
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Vendor / Customer master ----------

_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]$")
_PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")


def _mask_account_number(raw: str) -> str:
    """The column is named bank_account_masked for a reason — never persist
    a full account number. Keeps only the last 4 digits, matching the
    conventional display format (e.g. 'XXXXXXXX1234')."""
    digits_only = "".join(ch for ch in raw if ch.isalnum())
    if len(digits_only) <= 4:
        return "X" * len(digits_only)
    return "X" * (len(digits_only) - 4) + digits_only[-4:]


def parse_party_master(df: pd.DataFrame, kind: str) -> ParseResult:
    dataset = "vendor_master" if kind == "vendor" else "customer_master"
    df = normalize_columns(df, dataset)
    issues: list[ValidationIssue] = []
    valid_rows = []
    seen_names = set()

    if "name" not in df.columns:
        issues.append(ValidationIssue(0, None, "Missing required column: name", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        name = str(row.get("name", "")).strip()
        gstin = _clean_str(row.get("gstin"))
        pan = _clean_str(row.get("pan"))
        if gstin:
            gstin = gstin.upper()
        if pan:
            pan = pan.upper()

        if not name or name.lower() == "nan":
            issues.append(ValidationIssue(rn, "name", "Party name is missing", "ERROR", raw))
            continue

        if gstin and not _GSTIN_RE.match(gstin):
            issues.append(ValidationIssue(rn, "gstin", f"GSTIN '{gstin}' does not match the expected format", "WARNING", raw))
        if pan and not _PAN_RE.match(pan):
            issues.append(ValidationIssue(rn, "pan", f"PAN '{pan}' does not match the expected format", "WARNING", raw))

        key = _normalize_key(name)
        if key in seen_names:
            issues.append(ValidationIssue(rn, "name", f"Duplicate {kind} name '{name}' in this file — possible duplicate master record", "WARNING", raw))
        seen_names.add(key)

        valid_rows.append({
            "name": name, "gstin": gstin, "pan": pan,
            "address": _clean_str(row.get("address")),
            "bank_account": _mask_account_number(_clean_str(row.get("bank_account"))) if kind == "vendor" and _clean_str(row.get("bank_account")) else None,
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Sales / Purchase Register ----------

def parse_invoice_register(df: pd.DataFrame, direction: str) -> ParseResult:
    """direction: 'SALES' or 'PURCHASE'. Column layout is identical between
    the two registers — only which party (customer vs vendor) it links to,
    and the invoice.direction it's persisted under, differs."""
    df = normalize_columns(df, "invoice_register")
    issues: list[ValidationIssue] = []
    valid_rows = []
    seen_invoice_nos = set()

    required = {"invoice_no", "invoice_date", "party_name", "taxable_value"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)

        invoice_no = _clean_str(row.get("invoice_no"))
        party_name = _clean_str(row.get("party_name"))
        date = pd.to_datetime(row.get("invoice_date"), errors="coerce", dayfirst=True)
        taxable_value = pd.to_numeric(row.get("taxable_value"), errors="coerce")
        cgst = pd.to_numeric(row.get("cgst"), errors="coerce")
        sgst = pd.to_numeric(row.get("sgst"), errors="coerce")
        igst = pd.to_numeric(row.get("igst"), errors="coerce")
        cess = pd.to_numeric(row.get("cess"), errors="coerce")
        total_value = pd.to_numeric(row.get("total_value"), errors="coerce")
        gstin = _clean_str(row.get("gstin"))
        if gstin:
            gstin = gstin.upper()

        if not invoice_no:
            issues.append(ValidationIssue(rn, "invoice_no", "Invoice number is missing", "ERROR", raw))
            continue
        if not party_name:
            issues.append(ValidationIssue(rn, "party_name", "Party name is missing", "ERROR", raw))
            continue
        if pd.isna(date):
            issues.append(ValidationIssue(rn, "invoice_date", f"Unparseable date: {row.get('invoice_date')!r}", "ERROR", raw))
            continue
        if pd.isna(taxable_value) or taxable_value < 0:
            issues.append(ValidationIssue(rn, "taxable_value", "Taxable value is missing or negative", "ERROR", raw))
            continue

        cgst = 0.0 if pd.isna(cgst) else float(cgst)
        sgst = 0.0 if pd.isna(sgst) else float(sgst)
        igst = 0.0 if pd.isna(igst) else float(igst)
        cess = 0.0 if pd.isna(cess) else float(cess)
        computed_total = taxable_value + cgst + sgst + igst + cess

        if not pd.isna(total_value) and abs(total_value - computed_total) > 1.0:
            issues.append(ValidationIssue(
                rn, "total_value",
                f"Stated total {total_value:,.2f} does not equal taxable value + taxes {computed_total:,.2f}",
                "WARNING", raw,
            ))
        if gstin and not _GSTIN_RE.match(gstin):
            issues.append(ValidationIssue(rn, "gstin", f"GSTIN '{gstin}' does not match the expected format", "WARNING", raw))

        key = invoice_no.lower()
        if key in seen_invoice_nos:
            issues.append(ValidationIssue(rn, "invoice_no", f"Duplicate invoice number '{invoice_no}' in this file", "WARNING", raw))
        seen_invoice_nos.add(key)

        valid_rows.append({
            "direction": direction, "invoice_no": invoice_no, "invoice_date": date.date(),
            "party_name": party_name, "gstin": gstin,
            "taxable_value": float(taxable_value), "cgst": cgst, "sgst": sgst, "igst": igst, "cess": cess,
            "total_value": float(total_value) if not pd.isna(total_value) else computed_total,
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Bank Statement ----------

def parse_bank_statement(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "bank_statement")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"txn_date"}
    if not ({"debit", "credit"} & set(df.columns)):
        issues.append(ValidationIssue(0, None, "Missing debit/credit columns", "ERROR"))
        return ParseResult([], issues, len(df))
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)

        date = pd.to_datetime(row.get("txn_date"), errors="coerce", dayfirst=True)
        debit = pd.to_numeric(row.get("debit"), errors="coerce") if "debit" in df.columns else float("nan")
        credit = pd.to_numeric(row.get("credit"), errors="coerce") if "credit" in df.columns else float("nan")
        balance = pd.to_numeric(row.get("balance"), errors="coerce") if "balance" in df.columns else float("nan")
        description = _clean_str(row.get("description"))

        if pd.isna(date):
            issues.append(ValidationIssue(rn, "txn_date", f"Unparseable date: {row.get('txn_date')!r}", "ERROR", raw))
            continue

        debit_val = 0.0 if pd.isna(debit) else float(debit)
        credit_val = 0.0 if pd.isna(credit) else float(credit)

        if debit_val < 0 or credit_val < 0:
            issues.append(ValidationIssue(rn, "debit/credit", "Negative amount in a bank statement line", "ERROR", raw))
            continue
        if debit_val == 0 and credit_val == 0:
            issues.append(ValidationIssue(rn, "debit/credit", "Both debit and credit are zero", "WARNING", raw))
        if debit_val > 0 and credit_val > 0:
            issues.append(ValidationIssue(rn, "debit/credit", "Both debit and credit are non-zero on the same line (contra entry?)", "WARNING", raw))
        if not description:
            issues.append(ValidationIssue(rn, "description", "Transaction description is missing", "WARNING", raw))

        # Schema convention (bank_transaction.amount): positive = credit to
        # bank (money in), negative = debit (money out).
        amount = credit_val - debit_val

        valid_rows.append({
            "txn_date": date.date(),
            "description": description,
            "amount": amount,
            "balance_after": float(balance) if not pd.isna(balance) else None,
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- GST Return (GSTR-1 / GSTR-2B), invoice-level ----------
# Same shape as the sales/purchase register — a GST return is, structurally,
# just another invoice-level document set. Reusing parse_invoice_register's
# validation rules directly rather than duplicating them.

def parse_gst_return(df: pd.DataFrame, source: str) -> ParseResult:
    """source: 'GSTR1' or 'GSTR2B'."""
    return parse_invoice_register(df, source)


def parse_gstr3b_summary(df: pd.DataFrame) -> ParseResult:
    """GSTR-3B as filed is a period-level summary, not invoice-level — one
    row per return period with aggregate taxable value and tax heads."""
    df = normalize_columns(df, "gstr3b_summary")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"period", "taxable_value"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        period = _clean_str(row.get("period"))
        taxable_value = pd.to_numeric(row.get("taxable_value"), errors="coerce")

        if not period:
            issues.append(ValidationIssue(rn, "period", "Period is missing", "ERROR", raw))
            continue
        if pd.isna(taxable_value) or taxable_value < 0:
            issues.append(ValidationIssue(rn, "taxable_value", "Taxable value is missing or negative", "ERROR", raw))
            continue

        def _num(col):
            v = pd.to_numeric(row.get(col), errors="coerce")
            return 0.0 if pd.isna(v) else float(v)

        valid_rows.append({
            "period": period, "taxable_value": float(taxable_value),
            "cgst": _num("cgst"), "sgst": _num("sgst"), "igst": _num("igst"), "cess": _num("cess"),
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- TDS ledger / challan / return ----------

def parse_tds_ledger(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "tds_ledger")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"section", "tds_amount"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        section = _clean_str(row.get("section"))
        tds_amount = pd.to_numeric(row.get("tds_amount"), errors="coerce")
        deduction_date = pd.to_datetime(row.get("deduction_date"), errors="coerce", dayfirst=True)

        if not section:
            issues.append(ValidationIssue(rn, "section", "TDS section is missing", "ERROR", raw))
            continue
        if pd.isna(tds_amount) or tds_amount < 0:
            issues.append(ValidationIssue(rn, "tds_amount", "TDS amount is missing or negative", "ERROR", raw))
            continue

        pan = _clean_str(row.get("deductee_pan"))
        if pan and not _PAN_RE.match(pan.upper()):
            issues.append(ValidationIssue(rn, "deductee_pan", f"PAN '{pan}' does not match the expected format", "WARNING", raw))

        amt_paid = pd.to_numeric(row.get("amount_paid_credited"), errors="coerce")

        valid_rows.append({
            "section": section, "deductee_name": _clean_str(row.get("deductee_name")),
            "deductee_pan": pan.upper() if pan else None,
            "amount_paid_credited": float(amt_paid) if not pd.isna(amt_paid) else None,
            "tds_amount": float(tds_amount),
            "deduction_date": deduction_date.date() if not pd.isna(deduction_date) else None,
        })

    return ParseResult(valid_rows, issues, len(df))


def parse_tds_challan(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "tds_challan")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"section", "amount"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        section = _clean_str(row.get("section"))
        amount = pd.to_numeric(row.get("amount"), errors="coerce")
        challan_date = pd.to_datetime(row.get("challan_date"), errors="coerce", dayfirst=True)

        if not section:
            issues.append(ValidationIssue(rn, "section", "TDS section is missing", "ERROR", raw))
            continue
        if pd.isna(amount) or amount < 0:
            issues.append(ValidationIssue(rn, "amount", "Challan amount is missing or negative", "ERROR", raw))
            continue

        valid_rows.append({
            "section": section, "challan_no": _clean_str(row.get("challan_no")),
            "bsr_code": _clean_str(row.get("bsr_code")),
            "challan_date": challan_date.date() if not pd.isna(challan_date) else None,
            "amount": float(amount),
        })

    return ParseResult(valid_rows, issues, len(df))


def parse_tds_return(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "tds_return")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"section", "tds_amount"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        section = _clean_str(row.get("section"))
        tds_amount = pd.to_numeric(row.get("tds_amount"), errors="coerce")

        if not section:
            issues.append(ValidationIssue(rn, "section", "TDS section is missing", "ERROR", raw))
            continue
        if pd.isna(tds_amount) or tds_amount < 0:
            issues.append(ValidationIssue(rn, "tds_amount", "TDS amount is missing or negative", "ERROR", raw))
            continue

        valid_rows.append({
            "section": section, "deductee_pan": _clean_str(row.get("deductee_pan")),
            "tds_amount": float(tds_amount), "quarter": _clean_str(row.get("quarter")),
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Employee master / Payroll register ----------

def parse_employee_master(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "employee_master")
    issues: list[ValidationIssue] = []
    valid_rows = []
    seen_codes = set()

    if "name" not in df.columns:
        issues.append(ValidationIssue(0, None, "Missing required column: name", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        name = str(row.get("name", "")).strip()
        code = _clean_str(row.get("employee_code"))
        pan = _clean_str(row.get("pan"))
        doj = pd.to_datetime(row.get("date_of_joining"), errors="coerce", dayfirst=True)

        if not name or name.lower() == "nan":
            issues.append(ValidationIssue(rn, "name", "Employee name is missing", "ERROR", raw))
            continue
        if pan and not _PAN_RE.match(pan.upper()):
            issues.append(ValidationIssue(rn, "pan", f"PAN '{pan}' does not match the expected format", "WARNING", raw))
        if code:
            if code in seen_codes:
                issues.append(ValidationIssue(rn, "employee_code", f"Duplicate employee code '{code}' in this file", "WARNING", raw))
            seen_codes.add(code)

        valid_rows.append({
            "employee_code": code, "name": name, "pan": pan.upper() if pan else None,
            "uan": _clean_str(row.get("uan")),
            "date_of_joining": doj.date() if not pd.isna(doj) else None,
        })

    return ParseResult(valid_rows, issues, len(df))


def parse_payroll_register(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "payroll_register")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"employee_code", "period", "gross_salary"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        code = _clean_str(row.get("employee_code"))
        period = _clean_str(row.get("period"))
        gross = pd.to_numeric(row.get("gross_salary"), errors="coerce")

        if not code:
            issues.append(ValidationIssue(rn, "employee_code", "Employee code is missing", "ERROR", raw))
            continue
        if not period:
            issues.append(ValidationIssue(rn, "period", "Period is missing", "ERROR", raw))
            continue
        if pd.isna(gross) or gross < 0:
            issues.append(ValidationIssue(rn, "gross_salary", "Gross salary is missing or negative", "ERROR", raw))
            continue

        def _num(col):
            v = pd.to_numeric(row.get(col), errors="coerce")
            return 0.0 if pd.isna(v) else float(v)

        valid_rows.append({
            "employee_code": code, "period": period, "gross_salary": float(gross),
            "pf_employee": _num("pf_employee"), "pf_employer": _num("pf_employer"),
            "esi_employee": _num("esi_employee"), "esi_employer": _num("esi_employer"),
            "pt_amount": _num("pt_amount"),
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Fixed Asset Register ----------

def parse_fixed_asset_register(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "fixed_asset_register")
    issues: list[ValidationIssue] = []
    valid_rows = []
    seen_codes = set()

    required = {"description", "gross_block"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        description = _clean_str(row.get("description"))
        gross_block = pd.to_numeric(row.get("gross_block"), errors="coerce")
        code = _clean_str(row.get("asset_code"))

        if not description:
            issues.append(ValidationIssue(rn, "description", "Asset description is missing", "ERROR", raw))
            continue
        if pd.isna(gross_block) or gross_block < 0:
            issues.append(ValidationIssue(rn, "gross_block", "Gross block is missing or negative", "ERROR", raw))
            continue
        if code:
            if code in seen_codes:
                issues.append(ValidationIssue(rn, "asset_code", f"Duplicate asset code '{code}' in this file", "WARNING", raw))
            seen_codes.add(code)

        accum_dep = pd.to_numeric(row.get("accum_depreciation"), errors="coerce")
        accum_dep = 0.0 if pd.isna(accum_dep) else float(accum_dep)
        if accum_dep > gross_block:
            issues.append(ValidationIssue(rn, "accum_depreciation", "Accumulated depreciation exceeds gross block", "ERROR", raw))
            continue

        life = pd.to_numeric(row.get("useful_life_years"), errors="coerce")
        acq_date = pd.to_datetime(row.get("acquisition_date"), errors="coerce", dayfirst=True)
        disp_date = pd.to_datetime(row.get("disposal_date"), errors="coerce", dayfirst=True)
        disp_proceeds = pd.to_numeric(row.get("disposal_proceeds"), errors="coerce")

        if life is not None and not pd.isna(life) and life <= 0:
            issues.append(ValidationIssue(rn, "useful_life_years", "Useful life must be positive", "WARNING", raw))

        valid_rows.append({
            "asset_code": code, "description": description,
            "category": _clean_str(row.get("category")),
            "acquisition_date": acq_date.date() if not pd.isna(acq_date) else None,
            "gross_block": float(gross_block), "accum_depreciation": accum_dep,
            "useful_life_years": float(life) if not pd.isna(life) else None,
            "depreciation_method": _clean_str(row.get("depreciation_method")),
            "disposal_date": disp_date.date() if not pd.isna(disp_date) else None,
            "disposal_proceeds": float(disp_proceeds) if not pd.isna(disp_proceeds) else None,
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Inventory Register ----------

def parse_inventory_register(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "inventory_register")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"description", "quantity_on_hand"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        description = _clean_str(row.get("description"))
        qty = pd.to_numeric(row.get("quantity_on_hand"), errors="coerce")

        if not description:
            issues.append(ValidationIssue(rn, "description", "Item description is missing", "ERROR", raw))
            continue
        if pd.isna(qty):
            issues.append(ValidationIssue(rn, "quantity_on_hand", "Quantity is missing", "ERROR", raw))
            continue
        if qty < 0:
            issues.append(ValidationIssue(rn, "quantity_on_hand", "Negative stock quantity — investigate before relying on this figure", "ERROR", raw))
            continue

        unit_cost = pd.to_numeric(row.get("unit_cost"), errors="coerce")
        nrv = pd.to_numeric(row.get("nrv"), errors="coerce")
        ageing = pd.to_numeric(row.get("ageing_days"), errors="coerce")

        valid_rows.append({
            "item_code": _clean_str(row.get("item_code")), "description": description,
            "quantity_on_hand": float(qty),
            "unit_cost": float(unit_cost) if not pd.isna(unit_cost) else None,
            "nrv": float(nrv) if not pd.isna(nrv) else None,
            "ageing_days": int(ageing) if not pd.isna(ageing) else None,
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Loan Register ----------

def parse_loan_register(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "loan_register")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"lender_or_borrower", "direction", "principal_amount"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        party = _clean_str(row.get("lender_or_borrower"))
        direction = _clean_str(row.get("direction"))
        principal = pd.to_numeric(row.get("principal_amount"), errors="coerce")

        if not party:
            issues.append(ValidationIssue(rn, "lender_or_borrower", "Lender/borrower name is missing", "ERROR", raw))
            continue
        if direction:
            direction = direction.upper()
        if direction not in ("BORROWING", "LENDING"):
            issues.append(ValidationIssue(rn, "direction", f"Direction must be BORROWING or LENDING, got {direction!r}", "ERROR", raw))
            continue
        if pd.isna(principal) or principal < 0:
            issues.append(ValidationIssue(rn, "principal_amount", "Principal amount is missing or negative", "ERROR", raw))
            continue

        rate = pd.to_numeric(row.get("interest_rate"), errors="coerce")
        outstanding = pd.to_numeric(row.get("outstanding_balance"), errors="coerce")
        start = pd.to_datetime(row.get("start_date"), errors="coerce", dayfirst=True)
        maturity = pd.to_datetime(row.get("maturity_date"), errors="coerce", dayfirst=True)

        outstanding_val = float(outstanding) if not pd.isna(outstanding) else float(principal)
        if outstanding_val > principal * 1.5:
            issues.append(ValidationIssue(rn, "outstanding_balance", "Outstanding balance is more than 1.5x the principal — check for a data entry error", "WARNING", raw))

        valid_rows.append({
            "lender_or_borrower": party, "direction": direction, "principal_amount": float(principal),
            "interest_rate": float(rate) if not pd.isna(rate) else None,
            "start_date": start.date() if not pd.isna(start) else None,
            "maturity_date": maturity.date() if not pd.isna(maturity) else None,
            "outstanding_balance": outstanding_val,
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Investment Register ----------

def parse_investment_register(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "investment_register")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"investee_name", "cost"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        name = _clean_str(row.get("investee_name"))
        cost = pd.to_numeric(row.get("cost"), errors="coerce")

        if not name:
            issues.append(ValidationIssue(rn, "investee_name", "Investee name is missing", "ERROR", raw))
            continue
        if pd.isna(cost) or cost < 0:
            issues.append(ValidationIssue(rn, "cost", "Cost is missing or negative", "ERROR", raw))
            continue

        fv = pd.to_numeric(row.get("fair_value"), errors="coerce")
        fv_date = pd.to_datetime(row.get("fair_value_date"), errors="coerce", dayfirst=True)

        valid_rows.append({
            "investee_name": name, "investment_type": _clean_str(row.get("investment_type")),
            "classification": _clean_str(row.get("classification")),
            "cost": float(cost), "fair_value": float(fv) if not pd.isna(fv) else None,
            "fair_value_date": fv_date.date() if not pd.isna(fv_date) else None,
        })

    return ParseResult(valid_rows, issues, len(df))


# ---------- Intercompany Ledger / Confirmation ----------
# Same parser handles both — a confirmation and a books ledger are
# structurally identical; only the dataset_type tag at persistence time
# distinguishes 'our records' from 'their records', same pattern as
# reusing parse_tds_challan for PF/ESI/PT challans in Phase 11.

def parse_intercompany_transactions(df: pd.DataFrame) -> ParseResult:
    df = normalize_columns(df, "intercompany_ledger")
    issues: list[ValidationIssue] = []
    valid_rows = []

    required = {"counterparty_name", "transaction_date", "amount"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        issues.append(ValidationIssue(0, None, f"Missing required column(s): {', '.join(sorted(missing_cols))}", "ERROR"))
        return ParseResult([], issues, len(df))

    for idx, row in df.iterrows():
        rn = idx + 2
        raw = _json_safe_row(row)
        counterparty = _clean_str(row.get("counterparty_name"))
        date = pd.to_datetime(row.get("transaction_date"), errors="coerce", dayfirst=True)
        amount = pd.to_numeric(row.get("amount"), errors="coerce")

        if not counterparty:
            issues.append(ValidationIssue(rn, "counterparty_name", "Counterparty name is missing", "ERROR", raw))
            continue
        if pd.isna(date):
            issues.append(ValidationIssue(rn, "transaction_date", f"Unparseable date: {row.get('transaction_date')!r}", "ERROR", raw))
            continue
        if pd.isna(amount) or amount == 0:
            issues.append(ValidationIssue(rn, "amount", "Amount is missing or zero", "ERROR", raw))
            continue

        currency = _clean_str(row.get("currency")) or "INR"
        if currency != "INR":
            issues.append(ValidationIssue(rn, "currency", f"Non-INR currency '{currency}' — this system does not perform FX conversion; amount is used as-is", "WARNING", raw))

        valid_rows.append({
            "counterparty_name": counterparty, "transaction_type": _clean_str(row.get("transaction_type")),
            "transaction_date": date.date(), "amount": float(amount), "currency": currency,
            "reference_no": _clean_str(row.get("reference_no")),
        })

    return ParseResult(valid_rows, issues, len(df))
