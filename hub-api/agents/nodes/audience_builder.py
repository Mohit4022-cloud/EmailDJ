"""
Audience Builder Node — set intersection, scoring, and enrichment.

IMPLEMENTATION INSTRUCTIONS:
1. Intersection logic:
   - If state["intent_data"] is not None:
     intersect crm_results ∩ intent_data by domain.
   - If state["intent_data"] is None:
     use crm_results directly.
2. Deduplication: deduplicate by account domain (lowercase, strip www.).
3. For each unique account:
   a. Fetch Context Vault data: context_vault.cache.get_or_fetch(account_id).
   b. Check vault freshness: if last_enriched_at > 90 days ago, set stale=True.
   c. Compute Quality Score (1–100):
      - CRM data completeness (40%): count non-null fields / total fields * 40
      - Context Vault richness (40%): score based on vault field population
        (0 if no vault, 40 if full company profile exists)
      - Engagement recency (20%): 20 if activity in last 30 days, 10 if 90 days,
        0 if older.
   d. Build AccountRecord dict with all available data + quality_score + stale flag.
4. Sort by quality_score descending (highest quality accounts first).
5. Store in state["audience"].
6. If audience is empty after dedup/intersection, append warning to state["errors"].
"""

from agents.state import AgentState


def audience_builder_node(state: AgentState) -> AgentState:
    # TODO: implement per instructions above
    raise NotImplementedError("audience_builder_node not yet implemented")
