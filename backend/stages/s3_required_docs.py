"""Country policies allow required types or alternative document groups."""

from .common import finding, result


def run(context):
    settings = context["settings"]
    country = settings["country_aliases"].get(context["form"].get("country"), context["form"].get("country"))
    policy = country if country in settings["required_docs"] else "EU" if country in settings["eu_countries"] else "OTHER"
    found = {item["doc_type"] for item in context.get("extracted", []) if item["confidence"] >= settings["extraction_confidence_min"]}
    findings = []
    for requirement in settings["required_docs"][policy]:
        alternatives = requirement if isinstance(requirement, list) else [requirement]
        if not found.intersection(alternatives):
            label = " or ".join(alternatives)
            findings.append(finding("documents", f"Required evidence missing for {country}: {label}.",
                                    {"policy": policy, "observed_types": sorted(found)}, f"Upload a readable {label}."))
    return result("Country-specific document requirements checked.", findings, {"country_policy": policy, "observed_types": sorted(found)})
