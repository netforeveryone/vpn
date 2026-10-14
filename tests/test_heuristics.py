from src.services.heuristics import heuristic_score, protocol_counts
from src.utils.proxy import parse_proxy_url


def test_china_reality_vision_scores_high():
    url = (
        "vless://00000000-0000-4000-8000-000000000001@example.com:443"
        "?type=tcp&security=reality&flow=xtls-rprx-vision&pbk=abc&sid=1"
        "#CN-Reality"
    )
    cfg = parse_proxy_url(url, 1)
    assert heuristic_score("cn", cfg) >= 9


def test_russia_mobile_name_bonus():
    url = (
        "vless://00000000-0000-4000-8000-000000000002@1.2.3.4:443"
        "?security=reality#RU-mobile"
    )
    cfg = parse_proxy_url(url, 1)
    assert heuristic_score("ru", cfg) >= 5


def test_protocol_counts():
    urls = [
        "vless://00000000-0000-4000-8000-000000000003@h:1?security=tls#x",
        "trojan://pass@h:2#y",
    ]
    counts = protocol_counts(urls)
    assert counts["vless"] == 1
    assert counts["trojan"] == 1
