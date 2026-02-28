"""
CRM Query Agent Node — agentic SOQL generation with reflection.

IMPLEMENTATION INSTRUCTIONS:
Implements the agentic reflection pattern (NOT single-pass):

Loop (max 3 retries):
  1. Generate SOQL query:
     - Use Tier 2 model (GPT-4o-mini) with the plan's CRM step description.
     - Prompt: "Generate a Salesforce SOQL query to: {step_description}.
       Known objects: Account, Opportunity, Contact, Task, Event.
       Return ONLY valid SOQL — no explanation."
  2. Validate SOQL syntax:
     - Check SELECT...FROM...WHERE structure with regex.
     - Validate object/field names against a known_schema dict (hardcode common
       Salesforce fields: Account.Name, Account.Industry, Opportunity.StageName,
       Opportunity.CloseDate, Opportunity.Amount, Contact.Email, Contact.Title).
     - If invalid: append error to reflection_log, continue to next retry.
  3. Execute via Salesforce REST API:
     - GET {SALESFORCE_INSTANCE_URL}/services/data/{API_VERSION}/query?q={soql}
     - Auth: Bearer token from env SALESFORCE_OAUTH_TOKEN.
     - If credentials not configured: return mock_data() with state["data_source"]="mock".
  4. Check result:
     - If totalSize == 0: reflect ("Query returned no results. Broaden criteria..."),
       retry with adjusted WHERE clause.
     - If required fields missing from records: reflect, add fields to SELECT.
     - If success: break loop.
5. Store results in state["crm_results"]. Append any reflection notes to state["errors"].
6. Graceful mock data for dev: return 5 realistic fake Account records with all
   standard fields populated.
"""

from agents.state import AgentState


def crm_query_agent_node(state: AgentState) -> AgentState:
    # TODO: implement per instructions above
    raise NotImplementedError("crm_query_agent_node not yet implemented")
