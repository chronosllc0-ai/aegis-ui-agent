from backend.security.virustotal import map_report_to_risk_tag


def test_map_report_to_risk_tag_malicious() -> None:
    report = {"data": {"attributes": {"last_analysis_stats": {"malicious": 2, "suspicious": 0, "harmless": 70, "undetected": 1}}}}
    assert map_report_to_risk_tag(report) == "malicious"


def test_map_report_to_risk_tag_suspicious() -> None:
    report = {"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "suspicious": 1, "harmless": 20, "undetected": 3}}}}
    assert map_report_to_risk_tag(report) == "suspicious"


def test_map_report_to_risk_tag_low_risk_and_pending() -> None:
    low_risk = {"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "suspicious": 0, "harmless": 0, "undetected": 10}}}}
    pending = {"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "suspicious": 0, "harmless": 0, "undetected": 0}}}}
    assert map_report_to_risk_tag(low_risk) == "low_risk"
    assert map_report_to_risk_tag(pending) == "scan_pending"
