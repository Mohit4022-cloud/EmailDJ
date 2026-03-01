import pytest


@pytest.mark.asyncio
async def test_deep_research_node_builds_state_from_crm_results():
    from agents.nodes.deep_research_agent import deep_research_agent_node

    state = {
        'vp_command': 'Acme Corp',
        'crm_results': [
            {
                'summary': 'Acme announced an AI automation program and is hiring a VP Operations leader.',
                'industry': 'SaaS',
                'source_url': 'https://example.com/acme-news',
            },
            {
                'notes': 'CFO requested cost controls while evaluating migration to Snowflake.',
                'source_url': 'https://example.com/acme-finance',
            },
        ],
    }

    out = await deep_research_agent_node(state)
    research = out['research']

    assert research['icp_fit_score'] >= 6
    assert any('AI' in item for item in research['key_initiatives'])
    assert any('Expansion hiring' in item or 'Executive sponsorship' in item for item in research['leadership_signals'])
    assert 'Snowflake' in research['tech_stack_hints']
    assert len(research['sources']) == 2
    assert research['research_date']
