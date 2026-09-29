import httpx

from pizza_tracker.doctor import Check, explain, format_checks, run_checks


def _req(url):
    return httpx.Request("GET", url)


def test_explain_maps_errors_to_fixes():
    blocked = httpx.ConnectError("proxy said no", request=_req("https://cwwp2.dot.ca.gov/x.json"))
    assert "cannot reach cwwp2.dot.ca.gov" in explain(blocked)
    denied = httpx.HTTPStatusError("x", request=_req("https://data.sec.gov/a"), response=httpx.Response(403))
    assert "data.sec.gov refused" in explain(denied) and "User-Agent" in explain(denied)


def test_one_failure_does_not_hide_the_rest():
    def check_good():
        return Check("good", "ok", "fine")

    def check_broken():
        raise httpx.ConnectError("nope", request=_req("https://overpass-api.de/api"))

    def check_unset():
        return Check("unset", "skip", "set KEY")

    results = run_checks([check_good, check_broken, check_unset])
    assert [r.status for r in results] == ["ok", "fail", "skip"]
    assert results[1].name == "broken" and "overpass-api.de" in results[1].detail
    out = format_checks(results)
    assert "✓  good" in out and "✗  broken" in out and "1/3 sources working" in out


def test_unconfigured_sources_skip_without_network(monkeypatch):
    from pizza_tracker import doctor

    blank = type("S", (), {"wsdot_access_code": "", "pa511_api_key": "", "contact_email": ""})()
    monkeypatch.setattr(doctor, "get_settings", lambda: blank)
    assert {c().status for c in (doctor.check_wsdot, doctor.check_511pa, doctor.check_edgar)} == {"skip"}
