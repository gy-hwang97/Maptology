from build.distribution_policy import load_policy, delivery_mode_for


def _policy_file(tmp_path):
    p = tmp_path / "policy.tsv"
    p.write_text(
        "acronym\tdelivery_mode\tlicense\tlicense_url\treason\n"
        "EFO\tmaptology_server\tApache-2.0\thttps://x\tallowed\n"
        "ABC\tbioportal_user\t\t\tpublic, unclear licence\n"
        "XYZ\tblocked\tCC-BY-NC-ND\t\tno derivs\n"
        "WUT\tbanana\t\t\ttypo in mode\n",
        encoding="utf-8",
    )
    return str(p)


def test_loads_rows_by_acronym(tmp_path):
    policy = load_policy(_policy_file(tmp_path))
    assert policy["EFO"]["delivery_mode"] == "maptology_server"
    assert policy["EFO"]["license"] == "Apache-2.0"
    assert policy["EFO"]["license_url"] == "https://x"
    assert policy["EFO"]["reason"] == "allowed"
    assert policy["ABC"]["delivery_mode"] == "bioportal_user"


def test_missing_file_returns_empty(tmp_path):
    assert load_policy(str(tmp_path / "nope.tsv")) == {}


def test_delivery_mode_defaults_to_blocked(tmp_path):
    policy = load_policy(_policy_file(tmp_path))
    assert delivery_mode_for(policy, "EFO") == "maptology_server"
    assert delivery_mode_for(policy, "ABC") == "bioportal_user"
    assert delivery_mode_for(policy, "XYZ") == "blocked"
    # unknown acronym -> blocked
    assert delivery_mode_for(policy, "NOPE") == "blocked"
    # unrecognized mode -> blocked
    assert delivery_mode_for(policy, "WUT") == "blocked"
