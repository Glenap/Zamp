"""Weighted risk signals and fictional-list screening."""

from datetime import date
import re
from backend.rules.names import name_score
from .common import finding, result


def run(context):
    form, settings = context["form"], context["settings"]
    findings, signals = [], {}
    name = form.get("legal_name", "")
    for field, signal in (("tax_id", "duplicate_tax_id"), ("bank_account", "duplicate_bank_account"), ("iban", "duplicate_iban")):
        matches = [vendor for vendor in context["existing_vendors"] if form.get(field) and vendor.get(field)
                   and re.sub(r"\W", "", str(form[field]).upper()) == re.sub(r"\W", "", str(vendor[field]).upper())
                   and name_score(name, vendor["legal_name"]) < settings["name_match_threshold"]]
        signals[signal] = {"triggered": bool(matches), "detail": f"{field} matches a different entity." if matches else "No conflicting existing entity found.",
                           "evidence": [{"id": v["id"], "legal_name": v["legal_name"]} for v in matches]}
        if matches:
            findings.append(finding(field, f"Possible identity/bank-detail fraud: {field} matches a different existing vendor.", signals[signal]["evidence"],
                                    "Independently verify ownership and resolve conflicting registry records.", "reject"))
    sanctions = [entity for entity in settings["sanctions_list"] if name_score(name, entity) >= settings["sanctions_name_match_threshold"]]
    signals["sanctions_match"] = {"triggered": bool(sanctions), "detail": "Match in fictional sanctions fixture list." if sanctions else "No configured sanctions-list match.", "evidence": sanctions}
    if sanctions:
        findings.append(finding("legal_name", "Entity matches configured mock sanctions list.", sanctions, "Escalate to compliance for independent screening before onboarding.", "reject"))
    country = settings["country_aliases"].get(form.get("country"), form.get("country"))
    signals["high_risk_jurisdiction"] = {"triggered": country in settings["high_risk_jurisdictions"], "detail": "Fictional high-risk jurisdiction policy."}
    signals["po_box_only"] = {"triggered": bool(re.search(r"\bp\.?\s*o\.?\s*box\b", str(form.get("address", "")), re.I)), "detail": "PO-box address supplied."}
    try:
        age = (context["reference_date"] - date.fromisoformat(form.get("incorporated_on", ""))).days
        spend = float(form.get("estimated_annual_spend", form.get("annual_spend", 0)) or 0)
        recent_spend = 0 <= age < settings["new_company_days"] and spend >= settings["high_spend_threshold"]
    except (ValueError, TypeError):
        age, recent_spend = None, False
    signals["recent_company_high_spend"] = {"triggered": recent_spend, "detail": f"Company age {age} days; spend compared to configured threshold."}
    iban_country = str(form.get("iban") or "")[:2]
    signals["foreign_bank"] = {"triggered": bool(iban_country and country and iban_country != country), "detail": "IBAN country differs from entity country."}
    breakdown = [{"signal": key, "weight": weight, **signals.get(key, {"triggered": False, "detail": "Not applicable."})}
                 for key, weight in settings["risk_signal_weights"].items()]
    score = min(settings["max_risk_score"], sum(item["weight"] for item in breakdown if item["triggered"]))
    for item in breakdown:
        if item["triggered"] and item["signal"] not in ("sanctions_match", "duplicate_tax_id", "duplicate_bank_account", "duplicate_iban"):
            findings.append(finding(item["signal"], item["detail"], {"weight": item["weight"]}, "Investigate this risk signal and record supporting evidence."))
    context["risk_score"], context["risk_breakdown"] = score, breakdown
    return result("Risk indicators scored using stored configuration.", findings,
                  {"risk_score": score, "risk_breakdown": breakdown, "company_age_days": age, "sanctions_list_is_mock": True})
