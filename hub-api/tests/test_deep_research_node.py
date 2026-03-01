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


@pytest.mark.asyncio
async def test_deep_research_node_sparse_input_uses_fallback_signals():
    from agents.nodes.deep_research_agent import deep_research_agent_node

    out = await deep_research_agent_node({'vp_command': 'UnknownCo', 'crm_results': []})
    research = out['research']

    assert research['sources'] == []
    assert research['leadership_signals']
    assert research['financial_signals']
    assert 1 <= research['icp_fit_score'] <= 10


@pytest.mark.asyncio
async def test_deep_research_node_dedupes_and_limits_sources():
    from agents.nodes.deep_research_agent import deep_research_agent_node

    state = {
        'vp_command': 'Acme Corp',
        'crm_results': [
            {'summary': 'Expansion plan announced.', 'source_url': 'https://example.com/a'},
            {'summary': 'AI roadmap launched.', 'source_url': 'https://example.com/a'},
            {'summary': 'Security review in progress.', 'source_url': 'https://example.com/b'},
        ],
        'research_inputs': [
            {'snippet': 'Cost optimization program', 'source_url': 'https://example.com/b'},
            {'snippet': 'New cloud migration initiative', 'source_url': 'https://example.com/c'},
        ],
    }
    out = await deep_research_agent_node(state)
    research = out['research']

    assert research['sources'] == ['https://example.com/a', 'https://example.com/b', 'https://example.com/c']
    assert len(research['sources']) == len(set(research['sources']))


@pytest.mark.asyncio
async def test_deep_research_node_conflicting_signals_stays_bounded():
    from agents.nodes.deep_research_agent import deep_research_agent_node

    state = {
        'vp_command': 'Contoso',
        'crm_results': [
            {'summary': 'Contoso announced expansion hiring and AI investment.', 'source_url': 'https://example.com/expansion'},
            {'notes': 'Contoso announced layoffs and hard cost freezes.', 'source_url': 'https://example.com/costs'},
            {'signal': 'Security review and migration pilot are both active.', 'source_url': 'https://example.com/security'},
        ],
    }

    out = await deep_research_agent_node(state)
    research = out['research']

    assert 1 <= research['icp_fit_score'] <= 10
    assert len(research['key_initiatives']) >= 1
    assert len(research['financial_signals']) >= 1
    assert len(research['sources']) == 3
