"""Shared result shape and finding severities."""


def finding(field, message, evidence=None, action="Request corrected evidence.", severity="review"):
    return {"field": field, "message": message, "evidence": evidence, "action": action, "severity": severity}


def result(summary, findings=None, data=None, status=None):
    findings = findings or []
    return {"summary": summary, "findings": findings, "data": data or {},
            "status": status or ("failed" if any(f["severity"] == "reject" for f in findings) else "warning" if findings else "passed")}
