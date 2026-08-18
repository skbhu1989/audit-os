"""
Vendor/Customer Master Data Intelligence (Sections 27-28).

Distinct from Phase 10's duplicate-vendor-NAME detection (fuzzy string
matching on the name itself). This module catches a different, arguably
more serious pattern: two DIFFERENT vendor/customer names sharing the same
PAN, GSTIN, or bank account — which under Indian tax law means they're
legally the same entity (PAN/GSTIN are unique per legal entity), so this is
a much higher-confidence signal than name similarity, not a softer version
of the same check.

Every finding follows Section 51's explicit "no black box" structure:
FACT / SOURCE DATA / RULE / ANALYSIS / CONCLUSION / CONFIDENCE / ACTION.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class MasterDataFinding:
    fact: str
    source_data: str
    rule: str
    analysis: str
    conclusion: str
    confidence: str  # 'HIGH' | 'MEDIUM'
    recommended_action: str
    party_ids: list[str] = field(default_factory=list)


def find_same_identifier_different_name(parties: list[dict], party_kind: str) -> list[MasterDataFinding]:
    """parties: [{'id','name','pan','gstin','bank_account_masked'}].
    Groups by each identifier independently — a shared PAN and a shared
    GSTIN are reported as separate findings even if they involve the same
    two parties, since they're independently meaningful facts an auditor
    would want to see stated separately, not silently merged."""
    findings = []

    for field_name, label, rule_text in [
        ("pan", "PAN", "Under the Income Tax Act, a PAN uniquely identifies one legal entity or individual."),
        ("gstin", "GSTIN", "A GSTIN is registered to one specific legal entity per state; it cannot legitimately belong to two unrelated businesses."),
        ("bank_account_masked", "bank account", "A bank account is opened by one specific account holder; two unrelated legal entities should not share one."),
    ]:
        groups: dict[str, list[dict]] = {}
        for p in parties:
            val = p.get(field_name)
            if not val:
                continue
            groups.setdefault(val, []).append(p)

        for val, group in groups.items():
            distinct_names = {p["name"].strip().lower() for p in group}
            if len(distinct_names) <= 1:
                continue  # same name, same identifier — not a finding, that's just one party correctly recorded

            names_list = ", ".join(sorted({p["name"] for p in group}))
            findings.append(MasterDataFinding(
                fact=f"{len(group)} {party_kind} records share the same {label} ({val}) but have different names: {names_list}.",
                source_data=f"{party_kind.capitalize()} master ({len(group)} records examined for shared {label}).",
                rule=rule_text,
                analysis=(
                    f"Since {label} uniquely identifies one legal entity, these {len(group)} records are very likely "
                    f"the same real-world {party_kind} entered under different names — whether due to a genuine "
                    f"duplicate master record, a rebranding not reflected consistently, or (in the higher-risk case) "
                    f"an attempt to disguise related-party or fictitious-vendor transactions as unrelated ones."
                ),
                conclusion=f"POTENTIAL DUPLICATE OR UNDISCLOSED RELATED {party_kind.upper()} RECORD REQUIRING FURTHER INVESTIGATION.",
                confidence="HIGH" if field_name in ("pan", "gstin") else "MEDIUM",
                recommended_action=(
                    f"Confirm with management why {names_list} share the same {label}; determine whether these "
                    f"should be merged into a single master record, and whether any resulting transactions require "
                    f"related-party disclosure."
                ),
                party_ids=[str(p["id"]) for p in group],
            ))

    return findings
