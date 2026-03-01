"""Provider interfaces and adapter resolution for campaign intelligence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import httpx


class ProviderConfigError(RuntimeError):
    """Raised when provider configuration is invalid for the selected mode."""


class ProviderExecutionError(RuntimeError):
    """Raised when a provider request fails at runtime."""


class CRMProvider(Protocol):
    name: str

    async def fetch_accounts(self, *, command: str) -> list[dict]:
        """Return CRM accounts relevant to the campaign command."""


class IntentProvider(Protocol):
    name: str

    async def fetch_intent(self, *, domains: list[str], command: str) -> list[dict]:
        """Return intent records for target domains."""


@dataclass(frozen=True)
class ProviderRuntime:
    primary: CRMProvider | IntentProvider
    fallback: CRMProvider | IntentProvider | None
    mode: str


def _clean_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _mode() -> str:
    return _clean_env("EMAILDJ_CAMPAIGN_INTELLIGENCE_MODE", "auto").lower() or "auto"


def _crm_provider_name() -> str:
    return _clean_env("EMAILDJ_CRM_PROVIDER", "salesforce").lower() or "salesforce"


def _intent_provider_name() -> str:
    return _clean_env("EMAILDJ_INTENT_PROVIDER", "bombora").lower() or "bombora"


def _valid_mode(mode: str) -> bool:
    return mode in {"auto", "real", "mock", "fallback"}


def _mock_accounts() -> list[dict]:
    return [
        {
            "account_id": f"001xx000000{i}",
            "name": f"Acme {i}",
            "industry": "SaaS",
            "website": f"https://acme{i}.example.com",
            "last_activity_days": i * 5,
        }
        for i in range(1, 6)
    ]


class MockCRMProvider:
    name = "mock"

    async def fetch_accounts(self, *, command: str) -> list[dict]:
        _ = command
        return _mock_accounts()


class MockIntentProvider:
    name = "mock"

    async def fetch_intent(self, *, domains: list[str], command: str) -> list[dict]:
        _ = command
        items: list[dict] = []
        for domain in domains:
            if not domain:
                continue
            items.append(
                {
                    "domain": domain,
                    "topics": ["sales productivity", "pipeline efficiency"],
                    "surge_score": 62,
                    "data_source": "mock",
                    "as_of_date": str(date.today()),
                }
            )
        return items


class SalesforceCRMProvider:
    name = "salesforce"

    def __init__(self, *, instance_url: str, access_token: str, api_version: str, timeout_seconds: float = 10.0):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds

    async def fetch_accounts(self, *, command: str) -> list[dict]:
        _ = command
        soql = (
            "SELECT Id, Name, Industry, Website, LastActivityDate "
            "FROM Account WHERE Website != null ORDER BY LastActivityDate DESC LIMIT 25"
        )
        url = f"{self.instance_url}/services/data/{self.api_version}/query"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"q": soql}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - network error shape varies by provider
            raise ProviderExecutionError(f"Salesforce CRM request failed: {exc}") from exc

        out: list[dict] = []
        for item in payload.get("records", []):
            out.append(
                {
                    "account_id": item.get("Id", ""),
                    "name": item.get("Name", ""),
                    "industry": item.get("Industry") or "",
                    "website": item.get("Website") or "",
                    "last_activity_date": item.get("LastActivityDate"),
                }
            )
        return out


class BomboraIntentProvider:
    name = "bombora"

    def __init__(self, *, api_key: str, api_url: str, timeout_seconds: float = 10.0):
        self.api_key = api_key
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds

    async def fetch_intent(self, *, domains: list[str], command: str) -> list[dict]:
        if not domains:
            return []
        body = {"domains": domains, "campaign_hint": command}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.api_url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - network error shape varies by provider
            raise ProviderExecutionError(f"Bombora intent request failed: {exc}") from exc

        records = payload.get("records", [])
        out: list[dict] = []
        for row in records:
            out.append(
                {
                    "domain": row.get("domain", ""),
                    "topics": row.get("topics", []),
                    "surge_score": row.get("surge_score", 0),
                    "data_source": "bombora",
                    "as_of_date": row.get("as_of_date") or str(date.today()),
                }
            )
        return out


def _build_real_crm_provider(name: str) -> CRMProvider | None:
    if name != "salesforce":
        return None

    instance_url = _clean_env("SALESFORCE_INSTANCE_URL")
    access_token = _clean_env("SALESFORCE_ACCESS_TOKEN")
    if not instance_url or not access_token:
        return None
    api_version = _clean_env("SALESFORCE_API_VERSION", "v59.0") or "v59.0"
    return SalesforceCRMProvider(
        instance_url=instance_url,
        access_token=access_token,
        api_version=api_version,
    )


def _build_real_intent_provider(name: str) -> IntentProvider | None:
    if name != "bombora":
        return None

    api_key = _clean_env("BOMBORA_API_KEY")
    api_url = _clean_env("BOMBORA_API_URL", "https://api.bombora.com/v1/company-surge")
    if not api_key:
        return None
    return BomboraIntentProvider(api_key=api_key, api_url=api_url)


def resolve_crm_provider_runtime() -> ProviderRuntime:
    mode = _mode()
    if not _valid_mode(mode):
        raise ProviderConfigError(
            "Invalid EMAILDJ_CAMPAIGN_INTELLIGENCE_MODE. Expected one of: auto, real, mock, fallback."
        )

    if mode == "mock":
        return ProviderRuntime(primary=MockCRMProvider(), fallback=None, mode=mode)

    real = _build_real_crm_provider(_crm_provider_name())
    if real is None:
        if mode == "real":
            raise ProviderConfigError("CRM provider mode is real but provider is not configured.")
        return ProviderRuntime(primary=MockCRMProvider(), fallback=None, mode=mode)

    if mode == "fallback":
        return ProviderRuntime(primary=real, fallback=MockCRMProvider(), mode=mode)
    return ProviderRuntime(primary=real, fallback=None, mode=mode)


def resolve_intent_provider_runtime() -> ProviderRuntime:
    mode = _mode()
    if not _valid_mode(mode):
        raise ProviderConfigError(
            "Invalid EMAILDJ_CAMPAIGN_INTELLIGENCE_MODE. Expected one of: auto, real, mock, fallback."
        )

    if mode == "mock":
        return ProviderRuntime(primary=MockIntentProvider(), fallback=None, mode=mode)

    real = _build_real_intent_provider(_intent_provider_name())
    if real is None:
        if mode == "real":
            raise ProviderConfigError("Intent provider mode is real but provider is not configured.")
        return ProviderRuntime(primary=MockIntentProvider(), fallback=None, mode=mode)

    if mode == "fallback":
        return ProviderRuntime(primary=real, fallback=MockIntentProvider(), mode=mode)
    return ProviderRuntime(primary=real, fallback=None, mode=mode)

