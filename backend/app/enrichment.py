from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from app.cache import TTLCache
from app.config import Settings
from app.openai_client import OpenAIClient
from app.prompts import tool_loop_system_prompt
from app.schemas import ContactProfile, SenderProfile, TargetAccountProfile
from app.tools import (
    as_citation,
    clean_json_text,
    extract_contact_profile,
    extract_published_at,
    extract_target_account_profile,
    fetch_url,
    resolve_domain,
    web_search,
)

ProgressCB = Callable[[str, dict[str, Any]], Awaitable[None]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_citations(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    citations = []
    for item in items or []:
        url = str(item.get("url") or "Unknown").strip() or "Unknown"
        citations.append(
            {
                "url": url,
                "retrieved_at": str(item.get("retrieved_at") or _now_iso()),
                "published_at": str(item.get("published_at") or "Unknown"),
            }
        )
    if citations:
        return citations
    return [{"url": "Unknown", "retrieved_at": _now_iso(), "published_at": "Unknown"}]


def _tool_defs(kind: str) -> list[dict[str, Any]]:
    extract_name = "extract_target_account_profile" if kind == "target" else "extract_contact_profile"
    return [
        {
            "type": "function",
            "function": {
                "name": "resolve_domain",
                "description": "Resolve official domain from company name and optional URL hint",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company_name": {"type": "string"},
                        "optional_url_hint": {"type": "string"},
                    },
                    "required": ["company_name"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web and return result metadata",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "recency_days": {"type": "integer"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["query", "recency_days", "max_results"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": "Fetch URL text content",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": extract_name,
                "description": "Extract structured profile from retrieved text blobs",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text_blobs": {
                            "type": "array",
                            "items": {"type": "object"},
                        }
                    },
                    "required": ["text_blobs"],
                    "additionalProperties": False,
                },
            },
        },
    ]


class EnrichmentService:
    def __init__(self, settings: Settings, openai: OpenAIClient):
        self.settings = settings
        self.openai = openai
        self.target_cache: TTLCache[dict[str, Any]] = TTLCache()
        self.news_cache: TTLCache[dict[str, Any]] = TTLCache()
        self.contact_cache: TTLCache[dict[str, Any]] = TTLCache()
        self.sender_cache: TTLCache[dict[str, Any]] = TTLCache()

    async def enrich_target(
        self,
        *,
        company_name: str | None,
        company_url: str | None,
        refresh: bool,
        progress: ProgressCB,
    ) -> TargetAccountProfile:
        trace_id = str(uuid4())
        await progress("progress", {"stage": "start", "message": "Starting target company enrichment."})

        domain_data = await resolve_domain(
            company_name=company_name or "",
            optional_url_hint=company_url,
            settings=self.settings,
            web_search_fn=lambda query, recency_days, max_results: web_search(
                query=query,
                recency_days=recency_days,
                max_results=max_results,
                settings=self.settings,
            ),
        )
        domain = str(domain_data.get("official_domain") or "Unknown")
        await progress("tool_result", {"tool": "resolve_domain", "official_domain": domain})

        cache_key = f"target:{domain.lower()}"
        if not refresh:
            cached = await self.target_cache.get(cache_key)
            if cached is not None:
                cached["last_refreshed_at"] = str(cached.get("last_refreshed_at") or _now_iso())
                await progress("progress", {"stage": "cache_hit", "message": "Loaded cached target profile."})
                return TargetAccountProfile(**cached)

        data = await self._run_tool_loop(
            kind="target",
            objective={
                "company_name": company_name,
                "company_url": company_url,
                "domain_hint": domain,
            },
            progress=progress,
        )
        citations_clean = _ensure_citations(list(data.get("citations") or []))

        payload = {
            "official_domain": data.get("official_domain") or domain,
            "confidence": float(data.get("confidence", domain_data.get("confidence", 0.0)) or 0.0),
            "products": list(data.get("products") or []),
            "summary": str(data.get("summary") or "Unknown"),
            "icp": str(data.get("ICP") or data.get("icp") or "Unknown"),
            "differentiators": list(data.get("differentiators") or []),
            "proof_points": list(data.get("proof_points") or []),
            "recent_news": list(data.get("recent_news") or []),
            "citations": citations_clean,
            "last_refreshed_at": _now_iso(),
            "raw_source_urls": [item.get("url", "") for item in citations_clean if item.get("url") and item.get("url") != "Unknown"],
            "tool_run_trace_id": trace_id,
        }
        profile = TargetAccountProfile(**payload)
        await self.target_cache.set(cache_key, profile.model_dump(), self.settings.target_ttl_seconds)
        await progress("progress", {"stage": "complete", "message": "Target company enrichment complete."})
        return profile

    async def enrich_contact(
        self,
        *,
        prospect_name: str,
        prospect_title: str | None,
        prospect_company: str | None,
        prospect_linkedin_url: str | None,
        target_company_name: str | None,
        target_company_url: str | None,
        refresh: bool,
        progress: ProgressCB,
    ) -> ContactProfile:
        trace_id = str(uuid4())
        await progress("progress", {"stage": "start", "message": "Starting prospect enrichment."})
        cache_key = f"contact:{prospect_name.strip().lower()}|{(prospect_company or '').strip().lower()}"
        if not refresh:
            cached = await self.contact_cache.get(cache_key)
            if cached is not None:
                await progress("progress", {"stage": "cache_hit", "message": "Loaded cached prospect profile."})
                return ContactProfile(**cached)

        data = await self._run_tool_loop(
            kind="contact",
            objective={
                "prospect_name": prospect_name,
                "prospect_title": prospect_title,
                "prospect_company": prospect_company,
                "prospect_linkedin_url": prospect_linkedin_url,
                "target_company_name": target_company_name,
                "target_company_url": target_company_url,
            },
            progress=progress,
        )
        citations_clean = _ensure_citations(list(data.get("citations") or []))

        inferred = list(data.get("inferred_kpis_or_priorities") or [])
        labeled_inferred = [item if item.lower().startswith("inference") else f"Inference: {item}" for item in inferred]

        payload = {
            "name": str(data.get("name") or prospect_name or "Unknown"),
            "current_title": str(data.get("current_title") or prospect_title or "Unknown"),
            "company": str(data.get("company") or prospect_company or "Unknown"),
            "role_summary": str(data.get("role_summary") or "Unknown"),
            "talking_points": list(data.get("talking_points") or []),
            "related_news": list(data.get("related_news") or []),
            "inferred_kpis_or_priorities": labeled_inferred,
            "citations": citations_clean,
            "confidence": float(data.get("confidence", 0.0) or 0.0),
            "last_refreshed_at": _now_iso(),
            "raw_source_urls": [item.get("url", "") for item in citations_clean if item.get("url") and item.get("url") != "Unknown"],
            "tool_run_trace_id": trace_id,
        }
        profile = ContactProfile(**payload)
        await self.contact_cache.set(cache_key, profile.model_dump(), self.settings.contact_ttl_seconds)
        await progress("progress", {"stage": "complete", "message": "Prospect enrichment complete."})
        return profile

    async def enrich_sender(
        self,
        *,
        company_name: str | None,
        current_product: str | None,
        company_notes: str | None,
        other_products: str | None,
        refresh: bool,
        progress: ProgressCB,
    ) -> SenderProfile:
        trace_id = str(uuid4())
        key = f"sender:{(company_name or '').strip().lower()}"
        if key and not refresh:
            cached = await self.sender_cache.get(key)
            if cached is not None:
                await progress("progress", {"stage": "cache_hit", "message": "Loaded cached sender profile."})
                return SenderProfile(**cached)

        await progress("progress", {"stage": "start", "message": "Structuring sender profile."})
        notes = (company_notes or "").strip()
        sentences = [part.strip() for part in notes.replace("\n", ". ").split(".") if part.strip()]
        proof_points = [line.strip(" -*") for line in (other_products or "").splitlines() if line.strip()][:5]
        profile = SenderProfile(
            company_name=company_name or "",
            structured_icp=sentences[0] if sentences else "",
            differentiation=sentences[1:4],
            proof_points=proof_points,
            notes_summary=(notes[:600] + "...") if len(notes) > 600 else notes,
            confidence=0.7 if notes else 0.3,
            citations=[],
            last_refreshed_at=_now_iso(),
            tool_run_trace_id=trace_id,
        )
        if key:
            await self.sender_cache.set(key, profile.model_dump(), self.settings.sender_ttl_seconds)
        await progress("progress", {"stage": "complete", "message": "Sender profile structured."})
        return profile

    async def _run_tool_loop(self, *, kind: str, objective: dict[str, Any], progress: ProgressCB) -> dict[str, Any]:
        # Fallback deterministic path if model unavailable.
        if not self.openai.enabled():
            await progress("progress", {"stage": "fallback", "message": "OpenAI unavailable; using deterministic enrichment fallback."})
            return await self._fallback_enrich(kind=kind, objective=objective, progress=progress)

        tools = _tool_defs(kind)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": tool_loop_system_prompt(kind)},
            {"role": "user", "content": json.dumps(objective)},
        ]
        fetched_blobs: list[dict[str, Any]] = []
        latest_extracted: dict[str, Any] | None = None

        for step in range(8):
            response = await self.openai.chat_completion(
                messages=messages,
                reasoning_effort=self.settings.openai_reasoning_high,
                tools=tools,
                tool_choice="auto",
                max_completion_tokens=900,
            )
            message = response.get("message") or {}
            tool_calls = list(message.get("tool_calls") or [])
            if tool_calls:
                messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
                for call in tool_calls:
                    fn = ((call.get("function") or {}).get("name") or "").strip()
                    args = clean_json_text(((call.get("function") or {}).get("arguments") or "{}"))
                    await progress("tool_call", {"step": step + 1, "tool": fn, "arguments": args})
                    output = await self._exec_tool(
                        kind=kind,
                        fn=fn,
                        args=args,
                        objective=objective,
                        fetched_blobs=fetched_blobs,
                        progress=progress,
                    )
                    if fn in {"extract_target_account_profile", "extract_contact_profile"} and isinstance(output, dict):
                        latest_extracted = output
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "content": json.dumps(output),
                        }
                    )
                    await progress("tool_result", {"step": step + 1, "tool": fn, "output": output})
                continue

            content = str(message.get("content") or "").strip()
            parsed = clean_json_text(content)
            if parsed:
                return parsed
            if latest_extracted:
                return latest_extracted

        if latest_extracted:
            return latest_extracted
        return await self._fallback_enrich(kind=kind, objective=objective, progress=progress)

    async def _exec_tool(
        self,
        *,
        kind: str,
        fn: str,
        args: dict[str, Any],
        objective: dict[str, Any],
        fetched_blobs: list[dict[str, Any]],
        progress: ProgressCB,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if fn == "resolve_domain":
            return await resolve_domain(
                company_name=str(args.get("company_name") or objective.get("target_company_name") or objective.get("company_name") or ""),
                optional_url_hint=str(args.get("optional_url_hint") or objective.get("target_company_url") or objective.get("company_url") or ""),
                settings=self.settings,
                web_search_fn=lambda query, recency_days, max_results: web_search(
                    query=query,
                    recency_days=recency_days,
                    max_results=max_results,
                    settings=self.settings,
                ),
            )
        if fn == "web_search":
            return await web_search(
                query=str(args.get("query") or ""),
                recency_days=int(args.get("recency_days") or 30),
                max_results=int(args.get("max_results") or 5),
                settings=self.settings,
            )
        if fn == "fetch_url":
            url = str(args.get("url") or "")
            fetched = await fetch_url(url)
            if fetched.get("content_text"):
                fetched_blobs.append(fetched)
            return fetched
        if fn == "extract_target_account_profile":
            text_blobs = list(args.get("text_blobs") or fetched_blobs)
            return await extract_target_account_profile(text_blobs, openai=self.openai, settings=self.settings)
        if fn == "extract_contact_profile":
            text_blobs = list(args.get("text_blobs") or fetched_blobs)
            return await extract_contact_profile(text_blobs, openai=self.openai, settings=self.settings)

        await progress("progress", {"stage": "tool_skip", "message": f"Unknown tool: {fn}"})
        return {}

    async def _fallback_enrich(self, *, kind: str, objective: dict[str, Any], progress: ProgressCB) -> dict[str, Any]:
        # Deterministic fallback still uses retrieval tools 1-3.
        if kind == "target":
            company_name = str(objective.get("company_name") or "")
            company_url = str(objective.get("company_url") or "")
            domain_data = await resolve_domain(
                company_name=company_name,
                optional_url_hint=company_url,
                settings=self.settings,
                web_search_fn=lambda query, recency_days, max_results: web_search(
                    query=query,
                    recency_days=recency_days,
                    max_results=max_results,
                    settings=self.settings,
                ),
            )
            domain = str(domain_data.get("official_domain") or "Unknown")
            results = await web_search(
                query=f"{company_name or domain} recent news products case studies",
                recency_days=30,
                max_results=5,
                settings=self.settings,
            )
            news_items = []
            blobs = []
            citations = []
            for row in results[:3]:
                url = str(row.get("url") or "")
                if not url:
                    continue
                citations.append(as_citation(url, extract_published_at(str(row.get("published_at") or row.get("snippet") or ""))))
                news_items.append(
                    {
                        "date": str(row.get("published_at") or "Unknown"),
                        "headline": str(row.get("title") or "Unknown"),
                        "why_it_matters": f"Why now: {str(row.get('snippet') or 'Recent public signal.')[:140]}",
                        "url": url,
                    }
                )
                fetched = await fetch_url(url)
                if fetched.get("content_text"):
                    blobs.append(fetched)
            extracted = await extract_target_account_profile(blobs or [{"url": item["url"], "retrieved_at": _now_iso(), "content_text": item["headline"]} for item in news_items], openai=self.openai, settings=self.settings)
            extracted.setdefault("official_domain", domain)
            extracted["recent_news"] = extracted.get("recent_news") or news_items
            extracted["citations"] = extracted.get("citations") or citations
            extracted.setdefault("confidence", float(domain_data.get("confidence", 0.25)))
            return extracted

        # contact fallback
        prospect_name = str(objective.get("prospect_name") or "")
        prospect_company = str(objective.get("prospect_company") or "")
        query = f"{prospect_name} {prospect_company} {objective.get('prospect_title') or ''}"
        results = await web_search(query=query, recency_days=365, max_results=5, settings=self.settings)
        blobs = []
        citations = []
        related_news = []
        for row in results[:3]:
            url = str(row.get("url") or "")
            if not url:
                continue
            citations.append(as_citation(url, extract_published_at(str(row.get("published_at") or row.get("snippet") or ""))))
            related_news.append(
                {
                    "date": str(row.get("published_at") or "Unknown"),
                    "headline": str(row.get("title") or "Unknown"),
                    "why_it_matters": f"Role relevance: {str(row.get('snippet') or 'Public signal.')[:140]}",
                    "url": url,
                }
            )
            fetched = await fetch_url(url)
            if fetched.get("content_text"):
                blobs.append(fetched)
        extracted = await extract_contact_profile(blobs or [{"url": item["url"], "retrieved_at": _now_iso(), "content_text": item["headline"]} for item in related_news], openai=self.openai, settings=self.settings)
        extracted.setdefault("name", prospect_name or "Unknown")
        extracted.setdefault("company", prospect_company or "Unknown")
        extracted.setdefault("current_title", str(objective.get("prospect_title") or "Unknown"))
        extracted["related_news"] = extracted.get("related_news") or related_news
        extracted["citations"] = extracted.get("citations") or citations
        extracted.setdefault("confidence", 0.25)
        return extracted
