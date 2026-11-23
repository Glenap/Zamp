"""Rejection precedes manual review; unresolved findings never approve."""

from .common import result


def decide(context):
    findings, score = context["findings"], context.get("risk_score", 0)
    bands = context["settings"]["risk_bands"]
    reject = any(item["severity"] == "reject" for item in findings) or score >= bands["high"][0]
    review = bool(findings) or score >= bands["medium"][0]
    decision = "REJECTED" if reject else "PENDING" if review else "APPROVED"
    reasons = [{"stage_no": item["stage_no"], "field": item["field"], "message": item["message"], "evidence": item.get("evidence")} for item in findings]
    confidences = [item["confidence"] for item in context.get("extracted", [])]
    confidence = min(confidences) if confidences and len(confidences) == len(context["documents"]) else 0.0
    return {"decision": decision, "risk_score": score, "risk_breakdown": context.get("risk_breakdown", []), "reasons": reasons,
            "what_would_change": list(dict.fromkeys(item["action"] for item in findings)), "confidence": confidence,
            "provider": context["provider"], "offline_demo": context["provider"] == "mock"}


def run(context):
    context["decision"] = decide(context)
    return result(f"Decision: {context['decision']['decision']}.", data=context["decision"])
