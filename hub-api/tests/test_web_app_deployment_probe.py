from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_probe_accepts_bundle_with_deployed_hub_url_and_preview_flag():
    import scripts.probe_web_app_deployment as probe

    responses = {
        "https://email.example.test/": probe.FetchResult(
            url="https://email.example.test/",
            status_code=200,
            text='<script type="module" src="/assets/index.js"></script>',
            content_type="text/html",
        ),
        "https://email.example.test/assets/index.js": probe.FetchResult(
            url="https://email.example.test/assets/index.js",
            status_code=200,
            text='const ENV={VITE_HUB_URL:"https://hub.example.test",VITE_PRESET_PREVIEW_PIPELINE:"off"};',
            content_type="application/javascript",
        ),
    }

    def fetcher(url: str, *, timeout_seconds: float):  # noqa: ARG001
        return responses[url]

    payload = probe.inspect_web_app_deployment("https://email.example.test", fetcher=fetcher)

    assert payload["client_bundle_usable"] is True
    assert payload["detected_vite_hub_url"] == "https://hub.example.test"
    assert payload["detected_preview_pipeline"] == "off"
    assert payload["clears_launch_blockers"] is False
    assert payload["failures"] == []


def test_probe_rejects_bundle_missing_hub_url_and_preview_flag():
    import scripts.probe_web_app_deployment as probe

    responses = {
        "https://email.example.test/": probe.FetchResult(
            url="https://email.example.test/",
            status_code=200,
            text='<script type="module" src="/assets/index.js"></script>',
            content_type="text/html",
        ),
        "https://email.example.test/assets/index.js": probe.FetchResult(
            url="https://email.example.test/assets/index.js",
            status_code=200,
            text='throw new Error("Missing VITE_HUB_URL for a production web-app build.")',
            content_type="application/javascript",
        ),
    }

    def fetcher(url: str, *, timeout_seconds: float):  # noqa: ARG001
        return responses[url]

    payload = probe.inspect_web_app_deployment("https://email.example.test", fetcher=fetcher)

    assert payload["client_bundle_usable"] is False
    assert "vite_hub_url_not_found_in_bundle" in payload["failures"]
    assert "vite_preview_pipeline_not_found_in_bundle" in payload["failures"]
    assert "missing_hub_url_runtime_error_present" in payload["warnings"]


def test_probe_reads_default_web_app_candidate_from_deployment_discovery(monkeypatch, tmp_path):
    import scripts.probe_web_app_deployment as probe

    discovery_path = tmp_path / "reports" / "launch" / "deployment_discovery.json"
    discovery_path.parent.mkdir(parents=True)
    discovery_path.write_text(
        """
{
  "found": true,
  "candidate_web_app_origin": "https://email.example.test/path",
  "usable_as_web_app_origin_candidate": true,
  "clears_launch_blockers": false
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "ROOT", tmp_path)

    assert probe._web_app_url_from_discovery() == "https://email.example.test"
