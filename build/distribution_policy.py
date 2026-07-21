"""Read the human-reviewed ontology distribution policy.

The policy file is the single source of truth for whether the Maptology server
may hand out a given ontology's cache. It is produced by the licence audit (a
separate effort); this module only reads it. Anything not explicitly allowed is
treated as blocked.
"""

import csv
import os

VALID_MODES = {"maptology_server", "bioportal_user", "blocked"}


def load_policy(path):
    """Read the policy TSV into ``{acronym: {...}}``. Missing file -> ``{}``."""
    if not os.path.exists(path):
        return {}
    policy = {}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            acronym = (row.get("acronym") or "").strip()
            if not acronym:
                continue
            policy[acronym] = {
                "delivery_mode": (row.get("delivery_mode") or "").strip(),
                "license": (row.get("license") or "").strip(),
                "license_url": (row.get("license_url") or "").strip(),
                "reason": (row.get("reason") or "").strip(),
            }
    return policy


def delivery_mode_for(policy, acronym):
    """Vetted delivery mode for one acronym; 'blocked' if absent or unrecognized."""
    entry = policy.get(acronym)
    if not entry:
        return "blocked"
    mode = entry.get("delivery_mode", "")
    return mode if mode in VALID_MODES else "blocked"
