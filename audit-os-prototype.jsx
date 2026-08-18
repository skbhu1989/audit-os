import React, { useState, useMemo } from "react";
import {
  LayoutDashboard, FileSpreadsheet, BookOpen, Users, UserCheck, Landmark,
  Receipt, ShieldCheck, ListChecks, FileText, MessagesSquare, Sparkles,
  AlertTriangle, CheckCircle2, TrendingUp, Search, ChevronRight, Info, Building2
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line
} from "recharts";

/* ============================== DESIGN TOKENS ============================== */
const C = {
  ink: "#10192B",
  ink2: "#1B2A47",
  inkLine: "#2C3C5E",
  paper: "#FAF9F4",
  paperLine: "#E2DECF",
  card: "#FFFFFF",
  slate: "#4B5568",
  faint: "#8892A4",
  gold: "#9C7A3C",
  goldSoft: "#EFE6D2",
  green: "#2E6E49",
  greenSoft: "#E4EFE7",
  amber: "#B8791E",
  amberSoft: "#F7ECD9",
  red: "#A93B3B",
  redSoft: "#F6E5E3",
  text: "#141B2B",
};
const serif = "Georgia, 'Iowan Old Style', 'Times New Roman', serif";
const mono = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
const sans = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

const inr = (n) =>
  "₹" + Math.round(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });

/* ============================== SEEDED RNG ============================== */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rnd = mulberry32(1729);
const pick = (arr) => arr[Math.floor(rnd() * arr.length)];

/* ============================== SYNTHETIC DATA ============================== */
function genData() {
  const tb = [
    { ledger: "Equity Share Capital", head: "Equity", fs: "Balance Sheet — Equity", credit: 50000000, debit: 0 },
    { ledger: "Reserves & Surplus", head: "Equity", fs: "Balance Sheet — Equity", credit: 187400000, debit: 0 },
    { ledger: "Term Loan — HDFC Bank", head: "Long-term Borrowings", fs: "Balance Sheet — Non-current Liabilities", credit: 62000000, debit: 0 },
    { ledger: "Trade Payables", head: "Current Liabilities", fs: "Balance Sheet — Current Liabilities", credit: 41250000, debit: 0 },
    { ledger: "GST Payable", head: "Current Liabilities", fs: "Balance Sheet — Current Liabilities", credit: 3120000, debit: 0 },
    { ledger: "TDS Payable", head: "Current Liabilities", fs: "Balance Sheet — Current Liabilities", credit: 940000, debit: 0 },
    { ledger: "Suspense Account", head: "Unclassified", fs: "UNMAPPED", credit: 0, debit: 612000, flag: "Suspense balance — requires classification before FS mapping" },
    { ledger: "Property, Plant & Equipment", head: "Non-current Assets", fs: "Balance Sheet — PPE", debit: 98600000, credit: 0 },
    { ledger: "Capital Work-in-Progress", head: "Non-current Assets", fs: "Balance Sheet — CWIP", debit: 12400000, credit: 0 },
    { ledger: "Investments — Non-current", head: "Non-current Assets", fs: "Balance Sheet — Investments", debit: 15000000, credit: 0 },
    { ledger: "Trade Receivables", head: "Current Assets", fs: "Balance Sheet — Current Assets", debit: 58300000, credit: 0 },
    { ledger: "Cash & Bank Balances", head: "Current Assets", fs: "Balance Sheet — Current Assets", debit: 21750000, credit: 0 },
    { ledger: "Inventories", head: "Current Assets", fs: "Balance Sheet — Current Assets", debit: 34600000, credit: 0 },
    { ledger: "Revenue from Operations", head: "Income", fs: "P&L — Revenue", credit: 312000000, debit: 0 },
    { ledger: "Other Income", head: "Income", fs: "P&L — Other Income", credit: 4100000, debit: 0 },
    { ledger: "Purchase of Stock-in-Trade", head: "Expenses", fs: "P&L — Expenses", debit: 168000000, credit: 0 },
    { ledger: "Employee Benefit Expense", head: "Expenses", fs: "P&L — Expenses", debit: 54200000, credit: 0 },
    { ledger: "Finance Costs", head: "Expenses", fs: "P&L — Expenses", debit: 7800000, credit: 0 },
    { ledger: "Depreciation & Amortisation", head: "Expenses", fs: "P&L — Expenses", debit: 11200000, credit: 0 },
    { ledger: "Other Expenses", head: "Expenses", fs: "P&L — Expenses", debit: 38900000, credit: 0 },
    { ledger: "Sundry Creditors — Advance (Dr)", head: "Current Liabilities", fs: "Balance Sheet — Current Liabilities", debit: 84000, credit: 0, flag: "Debit balance in a liability account — verify nature" },
  ];

  const users = ["A. Mehta (Accountant)", "R. Iyer (AP Executive)", "S. Kapoor (CFO)", "N. Rao (MD)", "P. Singh (Accountant)"];
  const jeAccounts = [
    ["Revenue from Operations", "Trade Receivables"],
    ["Trade Payables", "Bank Account"],
    ["Provision for Expenses", "Other Expenses"],
    ["Retained Earnings", "General Reserve"],
    ["Trade Receivables", "Revenue from Operations"],
    ["Miscellaneous Expenses", "Cash"],
    ["Suspense Account", "Trade Payables"],
    ["Inventories", "Purchase of Stock-in-Trade"],
    ["Related Party — Loan", "Bank Account"],
  ];
  const narrations = [
    "Being sales invoice booked", "Being vendor payment processed", "Being year-end provision reversed",
    "Being adjustment as per management instruction", "Being round-sum expense accrual",
    "Being inter-company balance write-back", "Being reclassification entry", "Being year-end revenue accrual",
  ];
  const je = [];
  for (let i = 0; i < 42; i++) {
    const day = 1 + Math.floor(rnd() * 31);
    const month = pick([3, 3, 3, 12, 6, 9, 1, 2, 3]); // bias toward March (year-end)
    const date = new Date(2026, month === 3 ? 2 : month - 1, Math.min(day, 28));
    const amount = Math.round((pick([1, 2, 5, 7.5, 10, 12.5, 15, 22, 25, 40]) * 100000));
    const [dr, cr] = pick(jeAccounts);
    const narration = pick(narrations);
    const user = pick(users);
    const dow = date.getDay();
    let score = 0;
    const reasons = [];
    if (amount % 500000 === 0) { score += 2; reasons.push("Round-number amount"); }
    if (dow === 0 || dow === 6) { score += 2; reasons.push("Posted on a weekend"); }
    if (date.getMonth() === 2 && date.getDate() >= 28) { score += 2; reasons.push("Posted in final days of financial year"); }
    if (user.includes("MD") || user.includes("CFO")) { score += 2; reasons.push("Posted directly by senior management (override risk)"); }
    if (narration.toLowerCase().includes("reversed") || narration.toLowerCase().includes("write-back")) { score += 2; reasons.push("Reversal / write-back entry"); }
    if (dr === "Suspense Account" || cr === "Suspense Account") { score += 1; reasons.push("Involves Suspense Account"); }
    let level = "LOW";
    if (score >= 6) level = "CRITICAL"; else if (score >= 4) level = "HIGH"; else if (score >= 2) level = "MEDIUM";
    je.push({
      id: `JE-${String(1000 + i)}`, date: date.toISOString().slice(0, 10), user,
      dr, cr, narration, amount, level, reasons: reasons.length ? reasons : ["No anomaly indicators identified"],
    });
  }

  const vendorNames = ["Om Sai Traders", "Bharat Steel Corp", "ABC Traders", "ABC Trader's Co", "Metro Logistics", "Suraj Packaging", "Vikas Enterprises", "Global Components Ltd", "Sunrise Chemicals", "Kiran Fabricators", "Aditya Freight Services", "Prime Electricals"];
  const ap = vendorNames.map((name, i) => {
    const outstanding = Math.round(pick([120000, 340000, 875000, 1560000, 2650000, 60000]) * (0.5 + rnd()));
    const age = pick([15, 45, 75, 130, 210, 400]);
    const bucket = age <= 30 ? "0–30" : age <= 60 ? "31–60" : age <= 90 ? "61–90" : age <= 180 ? "91–180" : age <= 365 ? "181–365" : ">365";
    return { id: `V-${i + 1}`, name, gstin: `27AAAC${1000 + i}A1Z${i % 9}`, outstanding, age, bucket,
      dup: name.startsWith("ABC Traders") || name.startsWith("ABC Trader's") };
  });

  const custNames = ["Nova Retail Pvt Ltd", "Everest Distributors", "Skyline Traders", "Coastal Marketing", "Anand Wholesale", "Vertex Industries", "Harmony Foods", "Krishna Agencies", "Falcon Exports", "Silverline Traders", "Bluewave Retail", "Zenith Enterprises"];
  const ar = custNames.map((name, i) => {
    const outstanding = Math.round(pick([95000, 410000, 980000, 2100000, 3400000, 5200000]) * (0.5 + rnd()));
    const age = pick([10, 40, 70, 150, 260, 400]);
    const bucket = age <= 30 ? "0–30" : age <= 60 ? "31–60" : age <= 90 ? "61–90" : age <= 180 ? "91–180" : age <= 365 ? "181–365" : ">365";
    return { id: `C-${i + 1}`, name, outstanding, age, bucket, ecl: age > 180 };
  });

  const bank = [
    { desc: "NEFT — Bharat Steel Corp", amt: 875000, status: "Matched" },
    { desc: "GST Challan — CPIN 26031X", amt: 312000, status: "Matched" },
    { desc: "Cheque #4521 issued 12-Feb, uncleared", amt: 145000, status: "Unreconciled — stale cheque >6 months" },
    { desc: "Fixed Deposit lien — Canara Bank", amt: 5000000, status: "Requires disclosure — lien not noted in books" },
    { desc: "RTGS from Everest Distributors", amt: 980000, status: "Matched" },
    { desc: "Transfer to related party — 30 Mar", amt: 1200000, status: "Flagged — related party transfer near year-end" },
    { desc: "TDS Challan — Sec 194C", amt: 84000, status: "Matched" },
    { desc: "Unidentified credit — narration blank", amt: 236000, status: "Unreconciled — source unidentified" },
  ];

  const gstRecon = [
    { type: "Books vs Sales Register", period: "Mar-2026", books: 26800000, ret: 26800000, diff: 0, reason: "—", risk: "LOW" },
    { type: "Sales Register vs GSTR-1", period: "Mar-2026", books: 26800000, ret: 25260000, diff: 1540000, reason: "Export invoices reported with delay", risk: "MEDIUM" },
    { type: "GSTR-1 vs GSTR-3B", period: "Mar-2026", books: 25260000, ret: 24980000, diff: 280000, reason: "Credit note not reflected in 3B", risk: "MEDIUM" },
    { type: "Books vs GSTR-3B (Annual)", period: "FY 2025-26", books: 312000000, ret: 309820000, diff: 2180000, reason: "Cumulative turnover mismatch — requires reconciliation statement", risk: "HIGH" },
    { type: "Purchase Register vs GSTR-2B", period: "Mar-2026", books: 14200000, ret: 13640000, diff: 560000, reason: "Supplier has not filed GSTR-1; ITC at risk", risk: "HIGH" },
    { type: "GSTR-2B vs ITC claimed (3B)", period: "Mar-2026", books: 13640000, ret: 13910000, diff: -270000, reason: "Excess ITC claimed vs 2B — potential reversal exposure", risk: "CRITICAL" },
    { type: "E-invoice vs Sales Register", period: "Mar-2026", books: 26800000, ret: 26540000, diff: 260000, reason: "3 invoices raised without IRN generation", risk: "MEDIUM" },
    { type: "RCM liability vs ITC claimed", period: "Mar-2026", books: 180000, ret: 165000, diff: 15000, reason: "RCM under-accrued on GTA freight", risk: "MEDIUM" },
  ];

  const tdsRecon = [
    { section: "194C — Contractors", deducted: 620000, paid: 620000, returned: 620000, status: "Matched" },
    { section: "194J — Professional Fees", deducted: 415000, paid: 380000, returned: 380000, status: "Deduction without full payment — interest exposure" },
    { section: "194Q — Purchase of Goods", deducted: 210000, paid: 210000, returned: 190000, status: "Return under-reports deductee credit" },
    { section: "195 — Non-resident Payment", deducted: 96000, paid: 96000, returned: 96000, status: "Matched — 15CA/15CB on file" },
    { section: "192 — Salaries", deducted: 1840000, paid: 1840000, returned: 1840000, status: "Matched" },
    { section: "194I — Rent", deducted: 132000, paid: 118000, returned: 118000, status: "Short payment — 14,000 unpaid past due date" },
  ];

  const wp = [
    { id: "WP-REV-01", objective: "Test revenue cut-off and recognition criteria", assertion: "Cut-off, Occurrence", standard: "Ind AS 115 / SA 330", status: "In Review" },
    { id: "WP-AR-02", objective: "Ageing analysis and ECL assessment of trade receivables", assertion: "Valuation", standard: "Ind AS 109 / SA 540", status: "Draft" },
    { id: "WP-AP-03", objective: "Unrecorded liability search via subsequent payments", assertion: "Completeness", standard: "SA 330 / SA 501", status: "Draft" },
    { id: "WP-JE-04", objective: "Journal entry testing for management override risk", assertion: "Occurrence, Classification", standard: "SA 240", status: "Signed Off" },
    { id: "WP-GST-05", objective: "Reconciliation of books turnover with GSTR-1/3B", assertion: "Completeness, Accuracy", standard: "SA 500", status: "In Review" },
    { id: "WP-TDS-06", objective: "TDS deduction, payment and return reconciliation", assertion: "Compliance, Accuracy", standard: "Income Tax Act, SA 250", status: "Draft" },
    { id: "WP-BANK-07", objective: "Bank reconciliation and stale item review", assertion: "Existence, Completeness", standard: "SA 500", status: "Signed Off" },
    { id: "WP-GC-08", objective: "Going concern assessment based on liquidity and covenant review", assertion: "Presentation & Disclosure", standard: "SA 570", status: "Draft" },
  ];

  const queries = [
    { id: "Q-101", topic: "GST turnover difference of ₹21.8 lakh between books and GSTR-3B for FY 2025-26", status: "Open", risk: "HIGH" },
    { id: "Q-102", topic: "Excess ITC of ₹2.70 lakh claimed vs GSTR-2B for March 2026", status: "Client Query Raised", risk: "CRITICAL" },
    { id: "Q-103", topic: "Fixed deposit lien with Canara Bank not disclosed in notes", status: "Open", risk: "MEDIUM" },
    { id: "Q-104", topic: "Related party fund transfer of ₹12 lakh on 30 March — nature and approval", status: "Client Responded", risk: "HIGH" },
    { id: "Q-105", topic: "Short TDS payment of ₹14,000 under Section 194I", status: "Open", risk: "MEDIUM" },
    { id: "Q-106", topic: "Possible duplicate vendor: 'ABC Traders' vs 'ABC Trader's Co'", status: "Open", risk: "MEDIUM" },
  ];

  return { tb, je, ap, ar, bank, gstRecon, tdsRecon, wp, queries };
}

/* ============================== SMALL UI PRIMITIVES ============================== */
function RiskStamp({ level }) {
  const map = {
    LOW: { c: C.green, bg: C.greenSoft, label: "LOW" },
    MEDIUM: { c: C.amber, bg: C.amberSoft, label: "MEDIUM" },
    HIGH: { c: C.red, bg: C.redSoft, label: "HIGH" },
    CRITICAL: { c: "#7A1F1F", bg: "#F3D9D6", label: "CRITICAL" },
  };
  const s = map[level] || map.LOW;
  return (
    <span
      style={{
        display: "inline-block", fontFamily: mono, fontSize: 11, letterSpacing: "0.06em",
        fontWeight: 700, color: s.c, background: s.bg, border: `1px solid ${s.c}66`,
        borderRadius: 3, padding: "2px 7px", whiteSpace: "nowrap",
      }}
    >
      {s.label}
    </span>
  );
}

function StatusStamp({ status }) {
  const good = ["Matched", "Signed Off", "Closed", "Client Responded"].includes(status);
  const bad = status && (status.toLowerCase().includes("unreconciled") || status.toLowerCase().includes("flagged") || status.toLowerCase().includes("short") || status.toLowerCase().includes("without") || status.toLowerCase().includes("under-reports"));
  const c = bad ? C.red : good ? C.green : C.amber;
  return (
    <span style={{ fontFamily: sans, fontSize: 12, fontWeight: 600, color: c }}>
      {bad ? "⚠ " : good ? "✓ " : "● "}{status}
    </span>
  );
}

function Card({ title, eyebrow, children, right }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.paperLine}`, borderRadius: 6 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${C.paperLine}` }}>
        <div>
          {eyebrow && <div style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: "0.12em", color: C.gold, textTransform: "uppercase", marginBottom: 2 }}>{eyebrow}</div>}
          <div style={{ fontFamily: serif, fontSize: 16, color: C.text }}>{title}</div>
        </div>
        {right}
      </div>
      <div style={{ padding: 18 }}>{children}</div>
    </div>
  );
}

function Table({ columns, rows }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: sans, fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: c.align || "left", padding: "8px 10px", fontFamily: mono, fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase", color: C.faint, borderBottom: `1.5px solid ${C.text}`, whiteSpace: "nowrap" }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${C.paperLine}`, background: i % 2 ? "#FCFBF8" : "transparent" }}>
              {columns.map((c) => (
                <td key={c.key} style={{ padding: "8px 10px", textAlign: c.align || "left", color: c.muted ? C.faint : C.text, fontFamily: c.mono ? mono : sans, whiteSpace: "nowrap" }}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatBlock({ label, value, sub, accent }) {
  return (
    <div style={{ padding: "14px 16px", background: C.card, border: `1px solid ${C.paperLine}`, borderRadius: 6, borderTop: `3px solid ${accent || C.gold}` }}>
      <div style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase", color: C.faint }}>{label}</div>
      <div style={{ fontFamily: serif, fontSize: 24, color: C.text, marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontFamily: sans, fontSize: 12, color: C.faint, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

/* ============================== MODULES ============================== */
function Dashboard({ data }) {
  const riskCats = [
    ["Revenue", "MEDIUM"], ["Receivables", "MEDIUM"], ["Payables", "LOW"], ["Inventory", "LOW"],
    ["Cash & Bank", "MEDIUM"], ["GST", "HIGH"], ["TDS", "MEDIUM"], ["Related Parties", "HIGH"],
    ["Fraud Indicators", "LOW"], ["Going Concern", "LOW"], ["Financial Instruments", "LOW"], ["IFC", "MEDIUM"],
  ];
  const compliance = [
    { name: "GST", score: 78 }, { name: "TDS", score: 84 }, { name: "PF/ESI", score: 96 },
    { name: "Income Tax", score: 88 }, { name: "MCA", score: 93 },
  ];
  const funnel = [
    { stage: "Total Records", n: 4820 }, { stage: "Matched", n: 4390 },
    { stage: "Partially Matched", n: 240 }, { stage: "Unmatched", n: 190 },
  ];
  const critical = data.je.filter((j) => j.level === "CRITICAL" || j.level === "HIGH").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <StatBlock label="Audit Readiness" value="84%" sub="Top blocker: GST turnover reconciliation" accent={C.amber} />
        <StatBlock label="Material Exceptions" value={data.queries.filter(q => q.risk === "HIGH" || q.risk === "CRITICAL").length} sub="Requiring client response" accent={C.red} />
        <StatBlock label="High/Critical JE Risk" value={critical} sub={`of ${data.je.length} entries tested`} accent={C.red} />
        <StatBlock label="Overall Materiality" value={inr(4680000)} sub="1% of Revenue (benchmark)" accent={C.green} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 16 }}>
        <Card title="Statutory Compliance Score" eyebrow="Section 88">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={compliance} margin={{ left: -10 }}>
              <CartesianGrid stroke={C.paperLine} vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 12, fontFamily: sans }} axisLine={{ stroke: C.paperLine }} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11, fontFamily: mono }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontFamily: sans, fontSize: 12, border: `1px solid ${C.paperLine}` }} />
              <Bar dataKey="score" fill={C.gold} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Universal Reconciliation Funnel" eyebrow="Books → Returns → Govt Records">
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
            {funnel.map((f, i) => (
              <div key={f.stage}>
                <div style={{ display: "flex", justifyContent: "space-between", fontFamily: sans, fontSize: 12.5, marginBottom: 3 }}>
                  <span style={{ color: C.slate }}>{f.stage}</span>
                  <span style={{ fontFamily: mono, color: C.text }}>{f.n.toLocaleString("en-IN")}</span>
                </div>
                <div style={{ height: 8, background: C.paperLine, borderRadius: 4 }}>
                  <div style={{ height: 8, width: `${(f.n / funnel[0].n) * 100}%`, background: i === 3 ? C.red : i === 2 ? C.amber : C.gold, borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Risk Assessment by Category" eyebrow="Section 45 — Audit Dashboard">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          {riskCats.map(([name, level]) => (
            <div key={name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", border: `1px solid ${C.paperLine}`, borderRadius: 5 }}>
              <span style={{ fontFamily: sans, fontSize: 13, color: C.text }}>{name}</span>
              <RiskStamp level={level} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TrialBalanceView({ data }) {
  const totalDr = data.tb.reduce((s, r) => s + r.debit, 0);
  const totalCr = data.tb.reduce((s, r) => s + r.credit, 0);
  return (
    <Card title="Trial Balance — Ledger to FS Line Mapping" eyebrow="Section 16" right={<span style={{ fontFamily: mono, fontSize: 12, color: totalDr === totalCr ? C.green : C.red }}>{totalDr === totalCr ? "TB TIES ✓" : "TB DOES NOT TIE"}</span>}>
      <Table
        columns={[
          { key: "ledger", label: "Ledger" },
          { key: "fs", label: "FS Line" },
          { key: "debit", label: "Debit", align: "right", mono: true, render: (r) => (r.debit ? inr(r.debit) : "—") },
          { key: "credit", label: "Credit", align: "right", mono: true, render: (r) => (r.credit ? inr(r.credit) : "—") },
          { key: "flag", label: "Flag", render: (r) => r.flag ? <span style={{ color: C.red, fontSize: 12 }}><AlertTriangle size={12} style={{ display: "inline", marginRight: 4, verticalAlign: -2 }} />{r.flag}</span> : <span style={{ color: C.green, fontSize: 12 }}>Clean</span> },
        ]}
        rows={data.tb}
      />
    </Card>
  );
}

function GeneralLedgerView({ data }) {
  const [filter, setFilter] = useState("ALL");
  const rows = filter === "ALL" ? data.je : data.je.filter((j) => j.level === filter);
  return (
    <Card
      title="Journal Entry Testing"
      eyebrow="Section 18 — 100% Population Tested"
      right={
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ fontFamily: mono, fontSize: 12, border: `1px solid ${C.paperLine}`, borderRadius: 4, padding: "4px 8px", background: C.paper }}>
          {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      }
    >
      <Table
        columns={[
          { key: "id", label: "JE ID", mono: true },
          { key: "date", label: "Date", mono: true },
          { key: "user", label: "Posted By" },
          { key: "accounts", label: "Accounts", render: (r) => `${r.dr} → ${r.cr}` },
          { key: "amount", label: "Amount", align: "right", mono: true, render: (r) => inr(r.amount) },
          { key: "level", label: "Risk", render: (r) => <RiskStamp level={r.level} /> },
          { key: "reasons", label: "Basis", render: (r) => <span style={{ fontSize: 12, color: C.faint }}>{r.reasons.join("; ")}</span> },
        ]}
        rows={rows}
      />
    </Card>
  );
}

function AgeingCard({ title, rows, dupOrEcl }) {
  const buckets = ["0–30", "31–60", "61–90", "91–180", "181–365", ">365"];
  const totals = buckets.map((b) => rows.filter((r) => r.bucket === b).reduce((s, r) => s + r.outstanding, 0));
  return (
    <Card title={title} eyebrow="Ageing Analysis">
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={buckets.map((b, i) => ({ bucket: b, amt: totals[i] }))}>
          <CartesianGrid stroke={C.paperLine} vertical={false} />
          <XAxis dataKey="bucket" tick={{ fontSize: 11, fontFamily: mono }} axisLine={{ stroke: C.paperLine }} tickLine={false} />
          <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} width={40} tickFormatter={(v) => `${(v / 100000).toFixed(0)}L`} />
          <Tooltip formatter={(v) => inr(v)} contentStyle={{ fontFamily: sans, fontSize: 12 }} />
          <Bar dataKey="amt" fill={C.gold} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div style={{ marginTop: 12 }}>
        <Table
          columns={[
            { key: "name", label: "Party" },
            { key: "outstanding", label: "Outstanding", align: "right", mono: true, render: (r) => inr(r.outstanding) },
            { key: "bucket", label: "Ageing", mono: true },
            { key: "flag", label: "Flag", render: (r) => {
              const f = dupOrEcl === "dup" ? r.dup : r.ecl;
              return f ? <span style={{ color: C.red, fontSize: 12 }}>{dupOrEcl === "dup" ? "Possible duplicate vendor" : "ECL provisioning required"}</span> : <span style={{ color: C.green, fontSize: 12 }}>—</span>;
            }},
          ]}
          rows={rows}
        />
      </div>
    </Card>
  );
}

function BankView({ data }) {
  return (
    <Card title="Bank Reconciliation" eyebrow="Section 23">
      <Table
        columns={[
          { key: "desc", label: "Description" },
          { key: "amt", label: "Amount", align: "right", mono: true, render: (r) => inr(r.amt) },
          { key: "status", label: "Status", render: (r) => <StatusStamp status={r.status} /> },
        ]}
        rows={data.bank}
      />
    </Card>
  );
}

function GSTView({ data }) {
  return (
    <Card title="GST Reconciliation Matrix" eyebrow="Section 59 — Books → Returns → Govt Records">
      <Table
        columns={[
          { key: "type", label: "Reconciliation" },
          { key: "period", label: "Period", mono: true },
          { key: "books", label: "Books/Source", align: "right", mono: true, render: (r) => inr(r.books) },
          { key: "ret", label: "Return/Target", align: "right", mono: true, render: (r) => inr(r.ret) },
          { key: "diff", label: "Difference", align: "right", mono: true, render: (r) => <span style={{ color: r.diff === 0 ? C.green : C.red }}>{inr(r.diff)}</span> },
          { key: "reason", label: "Reason" },
          { key: "risk", label: "Risk", render: (r) => <RiskStamp level={r.risk} /> },
        ]}
        rows={data.gstRecon}
      />
    </Card>
  );
}

function TDSView({ data }) {
  return (
    <Card title="TDS Reconciliation" eyebrow="Section 65">
      <Table
        columns={[
          { key: "section", label: "Section" },
          { key: "deducted", label: "Deducted", align: "right", mono: true, render: (r) => inr(r.deducted) },
          { key: "paid", label: "Paid", align: "right", mono: true, render: (r) => inr(r.paid) },
          { key: "returned", label: "Reported in Return", align: "right", mono: true, render: (r) => inr(r.returned) },
          { key: "status", label: "Status", render: (r) => <StatusStamp status={r.status} /> },
        ]}
        rows={data.tdsRecon}
      />
    </Card>
  );
}

function SamplingView({ data }) {
  const pop = data.ap.slice().sort((a, b) => b.outstanding - a.outstanding);
  let cum = 0;
  const interval = Math.round(pop.reduce((s, r) => s + r.outstanding, 0) / 6);
  const sample = pop.map((r) => { cum += r.outstanding; return { ...r, cum }; }).filter((r, i) => i % 2 === 0).slice(0, 6);
  return (
    <Card title="Monetary Unit Sampling — Accounts Payable Population" eyebrow="Section 35">
      <p style={{ fontFamily: sans, fontSize: 13, color: C.slate, marginBottom: 12 }}>
        Population: {pop.length} vendor balances totalling {inr(pop.reduce((s, r) => s + r.outstanding, 0))}. Sampling interval: {inr(interval)}, based on performance materiality. Method: Monetary Unit Sampling with high-value items selected with certainty.
      </p>
      <Table
        columns={[
          { key: "name", label: "Vendor" },
          { key: "outstanding", label: "Balance", align: "right", mono: true, render: (r) => inr(r.outstanding) },
          { key: "cum", label: "Cumulative", align: "right", mono: true, render: (r) => inr(r.cum) },
        ]}
        rows={sample}
      />
    </Card>
  );
}

function WorkingPapersView({ data }) {
  return (
    <Card title="Audit Working Papers" eyebrow="Section 41 — Auto-Generated">
      <Table
        columns={[
          { key: "id", label: "WP ID", mono: true },
          { key: "objective", label: "Objective" },
          { key: "assertion", label: "FS Assertion" },
          { key: "standard", label: "Standard/SA", mono: true },
          { key: "status", label: "Status", render: (r) => <StatusStamp status={r.status} /> },
        ]}
        rows={data.wp}
      />
    </Card>
  );
}

function QueriesView({ data }) {
  return (
    <Card title="Client Query Register" eyebrow="Section 42 / 87 — Exception-Driven">
      <Table
        columns={[
          { key: "id", label: "Query ID", mono: true },
          { key: "topic", label: "Query" },
          { key: "risk", label: "Risk", render: (r) => <RiskStamp level={r.risk} /> },
          { key: "status", label: "Status", render: (r) => <StatusStamp status={r.status} /> },
        ]}
        rows={data.queries}
      />
    </Card>
  );
}

/* ============================== AI ASSISTANT ============================== */
function AIAssistant({ data }) {
  const [log, setLog] = useState([]);
  const [q, setQ] = useState("");

  const prompts = [
    "Find duplicate vendors",
    "Show journal entries posted at year-end",
    "Reconcile GST turnover with revenue",
    "Check whether TDS has been deducted correctly",
    "Which customers have long outstanding but no recovery?",
  ];

  function answer(question) {
    const t = question.toLowerCase();
    if (t.includes("duplicate") && t.includes("vendor")) {
      const dups = data.ap.filter((v) => v.dup);
      return {
        answer: `${dups.length} vendor pair(s) show name-similarity indicating a possible duplicate master record.`,
        used: dups.map((d) => d.name).join(", "),
        calc: "Fuzzy string match on vendor name (Levenshtein-style similarity) across the vendor master.",
        standard: "SA 240 (fraud risk — fictitious/duplicate vendors), IFC — Procure to Pay master data control",
        evidence: "Vendor master extract; no supporting KYC/PAN difference confirmed yet.",
        implication: "Risk of duplicate payment or fictitious vendor exposure.",
        procedure: "Request vendor KYC/PAN/bank details for both records; confirm whether one should be deactivated.",
      };
    }
    if ((t.includes("year") && t.includes("end")) || t.includes("31 march") || t.includes("march")) {
      const rows = data.je.filter((j) => j.date.startsWith("2026-03") && Number(j.date.slice(8, 10)) >= 28);
      return {
        answer: `${rows.length} journal entries were posted in the final days of the financial year (28–31 March 2026).`,
        used: rows.map((r) => r.id).join(", ") || "None in sample",
        calc: "Filter of full journal population by posting date within the last 4 days of FY 2025-26.",
        standard: "SA 240, SA 330 — heightened risk of management override at period-end",
        evidence: "Journal register extract with user, narration and amount.",
        implication: "Elevated risk of manual override, cut-off error, or earnings management.",
        procedure: "Obtain business rationale and supporting documentation for each entry above performance materiality.",
      };
    }
    if (t.includes("gst") && (t.includes("reconcil") || t.includes("turnover") || t.includes("revenue"))) {
      const mismatches = data.gstRecon.filter((r) => r.diff !== 0);
      const totalDiff = mismatches.reduce((s, r) => s + Math.abs(r.diff), 0);
      return {
        answer: `${mismatches.length} of ${data.gstRecon.length} GST reconciliation points show a mismatch, aggregate absolute difference ${inr(totalDiff)}.`,
        used: mismatches.map((m) => `${m.type} (${inr(m.diff)})`).join("; "),
        calc: "Books/source amount less return/target amount at each reconciliation point.",
        standard: "CGST Act & Rules; Ind AS 115/AS 9 revenue recognition; SA 500",
        evidence: "Sales register, GSTR-1, GSTR-3B, GSTR-2B extracts (synthetic).",
        implication: "Potential revenue completeness issue and/or GST short-payment / ITC exposure.",
        procedure: "Raise client query for each mismatch line; obtain reconciliation statement supporting the annual GSTR-9C.",
      };
    }
    if (t.includes("tds")) {
      const issues = data.tdsRecon.filter((r) => r.status !== "Matched" && !r.status.startsWith("Matched"));
      return {
        answer: `${issues.length} of ${data.tdsRecon.length} TDS sections tested show a deduction/payment/return exception.`,
        used: issues.map((i) => `${i.section}: ${i.status}`).join("; "),
        calc: "Cross-check of TDS deducted (books) vs TDS paid (challan) vs TDS reported (return) by section.",
        standard: "Income Tax Act, 1961 — Chapter XVII-B; SA 250",
        evidence: "TDS ledger, challan register, TDS return (synthetic extracts).",
        implication: "Interest under Sec 201(1A), possible disallowance under Sec 40(a)(ia) if short/non-deduction.",
        procedure: "Recompute interest exposure; confirm subsequent payment and revised return filing where applicable.",
      };
    }
    if (t.includes("customer") && (t.includes("outstanding") || t.includes("recover"))) {
      const rows = data.ar.filter((c) => c.ecl);
      return {
        answer: `${rows.length} customers have balances outstanding beyond 180 days with no recorded recovery.`,
        used: rows.map((r) => `${r.name} (${inr(r.outstanding)}, ${r.bucket} days)`).join("; "),
        calc: "Ageing bucket derived from invoice date to reporting date; ECL flag set where age > 180 days.",
        standard: "Ind AS 109 — Expected Credit Loss model; SA 540",
        evidence: "AR ageing report; no balance confirmations on file yet.",
        implication: "Possible understatement of ECL provision / overstatement of receivables.",
        procedure: "Request balance confirmations; assess recoverability and recompute ECL provision.",
      };
    }
    return null;
  }

  function ask(text) {
    const question = text ?? q;
    if (!question.trim()) return;
    const result = answer(question);
    setLog((l) => [...l, { question, result }]);
    setQ("");
  }

  return (
    <Card title="AI Audit Assistant" eyebrow="Section 46 — Evidence-Backed, Explainable">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        {prompts.map((p) => (
          <button key={p} onClick={() => ask(p)} style={{ fontFamily: sans, fontSize: 12, padding: "6px 10px", borderRadius: 14, border: `1px solid ${C.gold}`, background: C.goldSoft, color: C.gold, cursor: "pointer" }}>
            {p}
          </button>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="Ask a question about this engagement's data…"
          style={{ flex: 1, fontFamily: sans, fontSize: 13, padding: "9px 12px", border: `1px solid ${C.paperLine}`, borderRadius: 5 }}
        />
        <button onClick={() => ask()} style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: sans, fontSize: 13, padding: "9px 14px", borderRadius: 5, border: "none", background: C.ink, color: "white", cursor: "pointer" }}>
          <Search size={14} /> Ask
        </button>
      </div>

      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        {log.length === 0 && (
          <div style={{ fontFamily: sans, fontSize: 12.5, color: C.faint, display: "flex", gap: 6, alignItems: "flex-start" }}>
            <Info size={14} style={{ marginTop: 1 }} />
            Every answer is grounded in the datasets loaded into this engagement and shows its working. If the data doesn't support a conclusion, the assistant says so rather than guessing.
          </div>
        )}
        {log.slice().reverse().map((entry, i) => (
          <div key={i} style={{ border: `1px solid ${C.paperLine}`, borderRadius: 6, padding: 14, background: C.paper }}>
            <div style={{ fontFamily: serif, fontSize: 14, color: C.text, marginBottom: 8, fontStyle: "italic" }}>"{entry.question}"</div>
            {entry.result ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 6, fontFamily: sans, fontSize: 12.5 }}>
                <Row label="ANSWER" value={entry.result.answer} strong />
                <Row label="DATA USED" value={entry.result.used} mono />
                <Row label="CALCULATION" value={entry.result.calc} />
                <Row label="STANDARD / LAW" value={entry.result.standard} />
                <Row label="EVIDENCE" value={entry.result.evidence} />
                <Row label="AUDIT IMPLICATION" value={entry.result.implication} />
                <Row label="RECOMMENDED PROCEDURE" value={entry.result.procedure} />
              </div>
            ) : (
              <div style={{ fontFamily: mono, fontSize: 12.5, color: C.red }}>
                INSUFFICIENT INFORMATION TO CONCLUDE.
                <div style={{ color: C.faint, marginTop: 4 }}>INFORMATION REQUIRED: this query needs a dataset or document not yet loaded into this engagement (e.g. bank confirmations, 26AS, contracts). Try one of the suggested questions above, or connect the relevant source.</div>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
function Row({ label, value, strong, mono: m }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "150px 1fr", gap: 10 }}>
      <div style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: "0.06em", color: C.gold, textTransform: "uppercase", paddingTop: 1 }}>{label}</div>
      <div style={{ color: strong ? C.text : C.slate, fontWeight: strong ? 600 : 400, fontFamily: m ? mono : sans }}>{value}</div>
    </div>
  );
}

/* ============================== SHELL ============================== */
const NAV = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "tb", label: "Trial Balance", icon: FileSpreadsheet },
  { key: "gl", label: "General Ledger", icon: BookOpen },
  { key: "ap", label: "Accounts Payable", icon: Landmark },
  { key: "ar", label: "Accounts Receivable", icon: Users },
  { key: "bank", label: "Bank", icon: Building2 },
  { key: "gst", label: "GST Reconciliation", icon: Receipt },
  { key: "tds", label: "TDS Reconciliation", icon: ShieldCheck },
  { key: "sampling", label: "Audit Sampling", icon: ListChecks },
  { key: "wp", label: "Working Papers", icon: FileText },
  { key: "queries", label: "Queries", icon: MessagesSquare },
  { key: "ai", label: "AI Assistant", icon: Sparkles },
];

export default function App() {
  const data = useMemo(() => genData(), []);
  const [tab, setTab] = useState("dashboard");

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: C.paper, fontFamily: sans }}>
      <style>{`* { box-sizing: border-box; } body { margin: 0; }`}</style>

      {/* Sidebar */}
      <div style={{ width: 232, background: C.ink, color: "#fff", display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div style={{ padding: "20px 18px", borderBottom: `1px solid ${C.inkLine}` }}>
          <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: "0.18em", color: C.gold }}>AUDIT OPERATING SYSTEM</div>
          <div style={{ fontFamily: serif, fontSize: 19, marginTop: 4 }}>Statutory Ledger</div>
        </div>
        <div style={{ padding: "10px 10px", flex: 1, overflowY: "auto" }}>
          {NAV.map((n) => {
            const Icon = n.icon;
            const active = tab === n.key;
            return (
              <button
                key={n.key}
                onClick={() => setTab(n.key)}
                style={{
                  display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left",
                  padding: "9px 12px", marginBottom: 2, borderRadius: 4, border: "none", cursor: "pointer",
                  background: active ? C.ink2 : "transparent", color: active ? "#fff" : "#B7C1D6",
                  borderLeft: active ? `2px solid ${C.gold}` : "2px solid transparent",
                  fontFamily: sans, fontSize: 13,
                }}
              >
                <Icon size={15} />
                {n.label}
              </button>
            );
          })}
        </div>
        <div style={{ padding: 16, borderTop: `1px solid ${C.inkLine}`, fontFamily: mono, fontSize: 10.5, color: "#7C8AA6" }}>
          Every AI conclusion is explainable, evidence-backed and subject to reviewer sign-off.
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "16px 28px", borderBottom: `1px solid ${C.paperLine}`, background: C.card, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: "0.08em", color: C.faint, textTransform: "uppercase" }}>Engagement</div>
            <div style={{ fontFamily: serif, fontSize: 18, color: C.text }}>Meridian Fashions Pvt Ltd — Statutory Audit FY 2025–26</div>
          </div>
          <div style={{ display: "flex", gap: 22 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: mono, fontSize: 10, color: C.faint, textTransform: "uppercase" }}>Framework</div>
              <div style={{ fontFamily: sans, fontSize: 13, color: C.text }}>Ind AS (unlisted, net worth &gt; ₹250 Cr)</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: mono, fontSize: 10, color: C.faint, textTransform: "uppercase" }}>Data</div>
              <div style={{ fontFamily: sans, fontSize: 13, color: C.amber }}>Synthetic sample</div>
            </div>
          </div>
        </div>

        <div style={{ padding: 24, flex: 1 }}>
          {tab === "dashboard" && <Dashboard data={data} />}
          {tab === "tb" && <TrialBalanceView data={data} />}
          {tab === "gl" && <GeneralLedgerView data={data} />}
          {tab === "ap" && <AgeingCard title="Accounts Payable — Vendor Ageing" rows={data.ap} dupOrEcl="dup" />}
          {tab === "ar" && <AgeingCard title="Accounts Receivable — Customer Ageing" rows={data.ar} dupOrEcl="ecl" />}
          {tab === "bank" && <BankView data={data} />}
          {tab === "gst" && <GSTView data={data} />}
          {tab === "tds" && <TDSView data={data} />}
          {tab === "sampling" && <SamplingView data={data} />}
          {tab === "wp" && <WorkingPapersView data={data} />}
          {tab === "queries" && <QueriesView data={data} />}
          {tab === "ai" && <AIAssistant data={data} />}
        </div>
      </div>
    </div>
  );
}
