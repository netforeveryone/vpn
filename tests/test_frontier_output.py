import base64
import json

from src.resources.frontier_output import publish_frontier_files, subscription_body


def test_subscription_headers(tmp_path, monkeypatch):
    monkeypatch.setattr("src.resources.frontier_output.DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "src.resources.frontier_output.FRONTIER_DATA_FILES",
        {
            "cn": tmp_path / "cn.txt",
            "ru": tmp_path / "ru.txt",
            "ir": tmp_path / "ir.txt",
            "all": tmp_path / "all.txt",
        },
    )
    body = subscription_body(["vless://x"], "cn")
    assert "# profile-title: KRPray" in body
    assert "# profile-update-interval:" in body
    publish_frontier_files(
        {"cn": ["vless://a"], "ru": [], "ir": [], "all": ["vless://a"]},
        vantage_modes={"cn": "heuristic", "ru": "heuristic", "ir": "heuristic"},
        repository="org/repo",
    )
    meta = json.loads((tmp_path / "app_metadata.json").read_text())
    assert meta["countries"]["cn"]["count"] == 1
    b64 = (tmp_path / "cn.b64").read_text().strip()
    decoded = base64.b64decode(b64).decode()
    assert "profile-title" in decoded
