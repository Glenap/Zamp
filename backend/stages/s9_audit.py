"""Check durable prior stage rows."""

from .common import finding, result


def run(context):
    count = context["audit_count"]
    findings = [] if count == 8 else [finding("audit", "Prior stage audit incomplete.", count, "Investigate storage and rerun.")]
    return result("Audit finalized with evidence, timing and rule version.", findings,
                  {"prior_stage_count": count, "rule_version": context["settings"]["rule_version"]})
