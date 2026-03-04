from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.openai_client import OpenAIClient
from app.prompts import extract_contact_profile_prompt, extract_target_profile_prompt


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_domain(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if "//" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower().strip()
    host = host.removeprefix("www.")
    return host


def _extract_urls_from_text(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[^\s)\]>\"']+", text or "")))


async def resolve_domain(
    company_name: str,
    optional_url_hint: str | None,
    *,
    settings: Settings,
    web_search_fn,
) -> dict[str, Any]:
    hint_domain = _normalize_domain(optional_url_hint or "")
    candidates: list[dict[str, Any]] = []
    if hint_domain:
        candidates.append({"domain": hint_domain, "source": "url_hint", "confidence": 0.95})

    if company_name:
        query = f"{company_name} official website"
        search_hits = await web_search_fn(query=query, recency_days=3650, max_results=5)
        for item in search_hits:
            domain = _normalize_domain(item.get("url", ""))
            if not domain:
                continue
            score = 0.75
            title = str(item.get("title") or "").lower()
            if "official" in title or company_name.lower() in title:
                score += 0.1
            candidates.append({"domain": domain, "source": "search", "confidence": min(score, 0.95)})

    seen: set[str] = set()
    unique_candidates: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda c: float(c.get("confidence", 0.0)), reverse=True):
        domain = str(item.get("domain") or "").strip()
        if not domain or domain in seen:
            continue
        seen.add(domain)
        unique_candidates.append(item)

    if unique_candidates:
        top = unique_candidates[0]
        return {
            "official_domain": top["domain"],
            "confidence": float(top.get("confidence", 0.0)),
            "candidates": unique_candidates,
        }

    return {"official_domain": "Unknown", "confidence": 0.0, "candidates": []}


async def web_search(query: str, recency_days: int, max_results: int, *, settings: Settings) -> list[dict[str, Any]]:
    # Primary: Serper
    if settings.serper_api_key:
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": max(1, min(max_results, 10))},
                )
                resp.raise_for_status()
                data = resp.json()
            out: list[dict[str, Any]] = []
            for row in (data.get("organic") or [])[: max(1, min(max_results, 10))]:
                out.append(
                    {
                        "title": str(row.get("title") or "").strip(),
                        "url": str(row.get("link") or "").strip(),
                        "snippet": str(row.get("snippet") or "").strip(),
                        "published_at": str(row.get("date") or "Unknown"),
                    }
                )
            return [item for item in out if item["url"]]
        except Exception:
            pass

    # Fallback: Brave
    if settings.brave_search_api_key:
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": settings.brave_search_api_key, "Accept": "application/json"},
                    params={"q": query, "count": max(1, min(max_results, 10)), "freshness": f"pd:{max(1, recency_days)}"},
                )
                resp.raise_for_status()
                data = resp.json()
            rows = ((data.get("web") or {}).get("results") or [])[: max(1, min(max_results, 10))]
            out: list[dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "title": str(row.get("title") or "").strip(),
                        "url": str(row.get("url") or "").strip(),
                        "snippet": str(row.get("description") or "").strip(),
                        "published_at": str(row.get("age") or "Unknown"),
                    }
                )
            return [item for item in out if item["url"]]
        except Exception:
            pass

    return []


async def fetch_url(url: str) -> dict[str, Any]:
    retrieved_at = _now_iso()
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        text = resp.text
    except Exception:
        return {"url": url, "retrieved_at": retrieved_at, "content_text": ""}

    # Minimal HTML cleanup
    clean = re.sub(r"<script[\\s\\S]*?</script>", " ", text, flags=re.IGNORECASE)
    clean = re.sub(r"<style[\\s\\S]*?</style>", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\\s+", " ", clean).strip()
    if len(clean) > 20000:
        clean = clean[:20000]
    return {"url": url, "retrieved_at": retrieved_at, "content_text": clean}


def _target_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "official_domain": {"type": "string"},
            "products": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "ICP": {"type": "string"},
            "differentiators": {"type": "array", "items": {"type": "string"}},
            "proof_points": {"type": "array", "items": {"type": "string"}},
            "recent_news": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "date": {"type": "string"},
                        "headline": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                        "url": {"type": "string"},
                    },
                    "required": ["date", "headline", "why_it_matters", "url"],
                },
            },
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "url": {"type": "string"},
                        "retrieved_at": {"type": "string"},
                        "published_at": {"type": "string"},
                    },
                    "required": ["url", "retrieved_at", "published_at"],
                },
            },
            "confidence": {"type": "number"},
        },
        "required": [
            "official_domain",
            "products",
            "summary",
            "ICP",
            "differentiators",
            "proof_points",
            "recent_news",
            "citations",
            "confidence",
        ],
    }


def _contact_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "current_title": {"type": "string"},
            "company": {"type": "string"},
            "role_summary": {"type": "string"},
            "talking_points": {"type": "array", "items": {"type": "string"}},
            "related_news": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "date": {"type": "string"},
                        "headline": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                        "url": {"type": "string"},
                    },
                    "required": ["date", "headline", "why_it_matters", "url"],
                },
            },
            "inferred_kpis_or_priorities": {"type": "array", "items": {"type": "string"}},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "url": {"type": "string"},
                        "retrieved_at": {"type": "string"},
                        "published_at": {"type": "string"},
                    },
                    "required": ["url", "retrieved_at", "published_at"],
                },
            },
            "confidence": {"type": "number"},
        },
        "required": [
            "name",
            "current_title",
            "company",
            "role_summary",
            "talking_points",
            "related_news",
            "inferred_kpis_or_priorities",
            "citations",
            "confidence",
        ],
    }


async def extract_target_account_profile(text_blobs: list[dict[str, Any]], *, openai: OpenAIClient, settings: Settings) -> dict[str, Any]:
    if openai.enabled():
        try:
            payload = await openai.chat_json(
                messages=extract_target_profile_prompt(text_blobs),
                reasoning_effort=settings.openai_reasoning_high,
                schema_name="target_account_profile",
                schema=_target_schema(),
                max_completion_tokens=1200,
            )
            if payload:
                return payload
        except Exception:
            pass

    citations = []
    seen_urls: set[str] = set()
    merged_text = " ".join(str(item.get("content_text") or "") for item in text_blobs)
    for item in text_blobs:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        citations.append(
            {
                "url": url,
                "retrieved_at": str(item.get("retrieved_at") or _now_iso()),
                "published_at": str(item.get("published_at") or "Unknown"),
            }
        )

    keywords = []
    for token in re.findall(r"[A-Z][A-Za-z0-9&-]{3,}", merged_text):
        if token.lower() in {"unknown", "http", "https"}:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= 4:
            break

    return {
        "official_domain": "Unknown",
        "products": keywords[:3],
        "summary": (merged_text[:320] + "...") if len(merged_text) > 320 else (merged_text or "Unknown"),
        "ICP": "Unknown",
        "differentiators": keywords[:3],
        "proof_points": [],
        "recent_news": [],
        "citations": citations,
        "confidence": 0.3,
    }


async def extract_contact_profile(text_blobs: list[dict[str, Any]], *, openai: OpenAIClient, settings: Settings) -> dict[str, Any]:
    if openai.enabled():
        try:
            payload = await openai.chat_json(
                messages=extract_contact_profile_prompt(text_blobs),
                reasoning_effort=settings.openai_reasoning_high,
                schema_name="contact_profile",
                schema=_contact_schema(),
                max_completion_tokens=1000,
            )
            if payload:
                return payload
        except Exception:
            pass

    citations = []
    seen_urls: set[str] = set()
    merged_text = " ".join(str(item.get("content_text") or "") for item in text_blobs)
    for item in text_blobs:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        citations.append(
            {
                "url": url,
                "retrieved_at": str(item.get("retrieved_at") or _now_iso()),
                "published_at": str(item.get("published_at") or "Unknown"),
            }
        )

    name_match = re.search(r"([A-Z][a-z]+\s+[A-Z][a-z]+)", merged_text)
    title_guess = "Unknown"
    for candidate in ["CEO", "CISO", "CRO", "CTO", "VP", "Director", "Head"]:
        if candidate.lower() in merged_text.lower():
            title_guess = candidate
            break
    return {
        "name": name_match.group(1) if name_match else "Unknown",
        "current_title": title_guess,
        "company": "Unknown",
        "role_summary": (merged_text[:260] + "...") if len(merged_text) > 260 else (merged_text or "Unknown"),
        "talking_points": [
            "Align outreach with role priorities and dated initiatives.",
            "Anchor claims to public signals with citations.",
        ],
        "related_news": [],
        "inferred_kpis_or_priorities": ["Inference: reply quality", "Inference: pipeline velocity"],
        "citations": citations,
        "confidence": 0.25,
    }


def extract_published_at(snippet: str) -> str:
    snippet = (snippet or "").strip()
    if not snippet:
        return "Unknown"
    patterns = [r"\b\d{4}-\d{2}-\d{2}\b", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b"]
    for pattern in patterns:
        match = re.search(pattern, snippet, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return "Unknown"


def as_citation(url: str, published_at: str | None = None) -> dict[str, str]:
    return {
        "url": url,
        "retrieved_at": _now_iso(),
        "published_at": published_at or "Unknown",
    }


def clean_json_text(value: str) -> dict[str, Any]:
    text = (value or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
    return {}

