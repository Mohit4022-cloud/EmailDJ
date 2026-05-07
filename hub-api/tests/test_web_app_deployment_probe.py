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


def test_probe_passes_vercel_bypass_header_to_index_and_assets():
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
    seen_headers: list[dict[str, str] | None] = []

    def fetcher(url: str, *, timeout_seconds: float, headers: dict[str, str] | None = None):  # noqa: ARG001
        seen_headers.append(headers)
        return responses[url]

    payload = probe.inspect_web_app_deployment(
        "https://email.example.test",
        vercel_protection_bypass_configured=True,
        fetch_headers={probe.VERCEL_BYPASS_HEADER: "secret"},
        fetcher=fetcher,
    )

    assert payload["client_bundle_usable"] is True
    assert payload["vercel_protection_bypass_env"] == "VERCEL_AUTOMATION_BYPASS_SECRET"
    assert payload["vercel_protection_bypass_configured"] is True
    assert payload["vercel_protection_bypass_header"] == "x-vercel-protection-bypass"
    assert seen_headers == [
        {"x-vercel-protection-bypass": "secret"},
        {"x-vercel-protection-bypass": "secret"},
    ]


def test_probe_records_git_sha_provenance_and_blocks_mismatch():
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

    payload = probe.inspect_web_app_deployment(
        "https://email.example.test",
        source_git_sha="oldsha",
        workspace_git_sha="newsha",
        fetcher=fetcher,
    )

    assert payload["source_git_sha"] == "oldsha"
    assert payload["workspace_git_sha_at_probe"] == "newsha"
    assert payload["probe_matches_workspace_head"] is False
    assert "deployment_discovery_sha_mismatch_with_workspace_head" in payload["failures"]


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


def test_probe_labels_vercel_401_as_auth_or_protection_blocker():
    import scripts.probe_web_app_deployment as probe

    def fetcher(url: str, *, timeout_seconds: float):  # noqa: ARG001
        return probe.FetchResult(url=url, status_code=401, text="Authentication Required", error="http_error:401")

    payload = probe.inspect_web_app_deployment("https://email-example-user.vercel.app", fetcher=fetcher)

    assert payload["client_bundle_usable"] is False
    assert "http_error:401" in payload["failures"]
    assert "web_app_deployment_requires_auth" in payload["failures"]
    assert "web_app_deployment_requires_auth_or_vercel_protection_bypass" in payload["failures"]
    assert "vercel_protection_bypass_secret_missing" in payload["failures"]


def test_probe_labels_configured_vercel_bypass_401_as_rejected_or_stale():
    import scripts.probe_web_app_deployment as probe

    def fetcher(url: str, *, timeout_seconds: float):  # noqa: ARG001
        return probe.FetchResult(url=url, status_code=401, text="Authentication Required", error="http_error:401")

    payload = probe.inspect_web_app_deployment(
        "https://email-example-user.vercel.app",
        vercel_protection_bypass_configured=True,
        fetcher=fetcher,
    )

    assert "vercel_protection_bypass_secret_rejected_or_stale" in payload["failures"]


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


def test_probe_exit_code_stays_strict_unless_readout_allows_blocked():
    import scripts.probe_web_app_deployment as probe

    blocked_payload = {"client_bundle_usable": False}
    usable_payload = {"client_bundle_usable": True}

    assert probe._exit_code_for_probe(blocked_payload, allow_blocked=False) == 1
    assert probe._exit_code_for_probe(blocked_payload, allow_blocked=True) == 0
    assert probe._exit_code_for_probe(usable_payload, allow_blocked=False) == 0


def test_write_probe_marks_nonblocking_readout_mode(monkeypatch, tmp_path):
    import scripts.probe_web_app_deployment as probe

    def fake_inspect(*args, **kwargs):  # noqa: ARG001
        return {
            "generated_at": "2026-05-07T20:30:00Z",
            "web_app_url": "https://email.example.test",
            "normalized_web_app_origin": "https://email.example.test",
            "source_git_sha": "sha",
            "workspace_git_sha_at_probe": "sha",
            "probe_matches_workspace_head": True,
            "vercel_protection_bypass_env": probe.VERCEL_BYPASS_ENV,
            "vercel_protection_bypass_configured": False,
            "vercel_protection_bypass_header": None,
            "client_bundle_usable": False,
            "failures": ["web_app_deployment_requires_auth"],
            "warnings": [],
            "clears_launch_blockers": False,
            "launch_blocker_note": probe.LAUNCH_BLOCKER_NOTE,
        }

    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.setattr(probe, "_git_head_sha", lambda: "sha")
    monkeypatch.setattr(probe, "_web_app_url_from_discovery", lambda: "https://email.example.test")
    monkeypatch.setattr(probe, "inspect_web_app_deployment", fake_inspect)

    json_path, md_path, payload = probe.write_probe(allow_blocked_exit=True)

    assert json_path.exists()
    assert md_path.exists()
    assert payload["client_bundle_usable"] is False
    assert payload["probe_exit_allows_blocked"] is True
    assert payload["probe_exit_policy"] == "nonblocking_artifact_refresh"
    assert "Probe exit policy: `nonblocking_artifact_refresh`" in md_path.read_text(encoding="utf-8")
