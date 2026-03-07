export const SDR_PRESETS = [
  {
    id: 'straight_shooter',
    strategy_id: 'straight_shooter',
    name: 'Straight Shooter',
    frequency: 'Daily Volume',
    eqVibe: 'Direct / Tight',
    vibe: 'Direct wedge + proof + focused CTA.',
    sliders: { formal: 55, outcome: 45, long: 40, diplomatic: 35 },
    whyItWorks:
      'It is explicit about the problem and offer, then asks for a specific next step.',
    sampleEmail: {
      subject: 'Brand protection workflow for your team',
      body:
        'Hi [Name],\n\nQuick point: teams often miss high-risk listings when enforcement steps are split across tools.\n\nWe help legal teams tighten triage and escalation without adding process overhead.\n\nOpen to a 15-min call for a quick teardown + recommended workflow? Worth a look / Not a priority?\n\nBest,\n[My Name]',
    },
  },
  {
    id: 'headliner',
    strategy_id: 'headliner',
    name: 'Headliner',
    frequency: 'High Volume',
    eqVibe: 'Curiosity / Punchy',
    vibe: 'Curiosity headline + one wedge + concise evidence.',
    sliders: { formal: 45, outcome: 60, long: 35, diplomatic: 30 },
    whyItWorks:
      'It earns attention with a sharp hook and immediately narrows to one practical risk.',
    sampleEmail: {
      subject: 'One risk to close this quarter',
      body:
        'Hi [Name],\n\nOne pattern we keep seeing: enforcement queues grow faster than review capacity.\n\nThat gap usually creates avoidable exposure in marketplaces and social channels.\n\nOpen to a 15-min call so I can share a quick teardown + first workflow to automate? Worth a look / Not a priority?\n\nBest,\n[My Name]',
    },
  },
  {
    id: 'giver',
    strategy_id: 'giver',
    name: 'Giver',
    frequency: 'Medium-High',
    eqVibe: 'Helpful / Low Pressure',
    vibe: 'Offer deliverable first, then optional next step.',
    sliders: { formal: 40, outcome: 65, long: 45, diplomatic: 75 },
    whyItWorks:
      'Value-first framing lowers resistance and gives the prospect a concrete reason to reply.',
    sampleEmail: {
      subject: 'Can I send a quick teardown?',
      body:
        "Hi [Name],\n\nIf useful, I can send a short teardown of your likely risk surface and what we'd automate first.\n\nMost teams use it to prioritize week-one enforcement actions without extra meetings.\n\nWorth a look / Not a priority?\n\nThanks,\n[My Name]",
    },
  },
  {
    id: 'challenger',
    strategy_id: 'challenger',
    name: 'Challenger',
    frequency: 'Targeted',
    eqVibe: 'Contrarian / Risk-Reframe',
    vibe: 'Reframe cost of inaction with a contrarian insight.',
    sliders: { formal: 50, outcome: 25, long: 45, diplomatic: 20 },
    whyItWorks:
      'It challenges default assumptions and turns hidden risk into an immediate operating issue.',
    sampleEmail: {
      subject: 'The hidden cost of delay',
      body:
        'Hi [Name],\n\nContrarian view: the biggest enforcement risk is often not detection, but slow action routing.\n\nThat delay compounds exposure even when teams are monitoring actively.\n\nOpen to a 15-min call to compare your current flow with a tighter enforcement sequence? Worth a look / Not a priority?\n\nBest,\n[My Name]',
    },
  },
  {
    id: 'industry_insider',
    strategy_id: 'industry_insider',
    name: 'Industry Insider',
    frequency: 'Trigger-Based',
    eqVibe: 'Domain-Led / Analytical',
    vibe: 'Domain vocabulary + pattern we see + practical recommendation.',
    sliders: { formal: 60, outcome: 50, long: 70, diplomatic: 70 },
    whyItWorks:
      'It sounds informed by the operating context and gives usable guidance without hype.',
    sampleEmail: {
      subject: 'Pattern we see in enforcement ops',
      body:
        'Hi [Name],\n\nPattern we see in mature programs: takedown speed improves only when triage logic and escalation policy are designed together.\n\nWhen those stay separate, priority cases still queue too long.\n\nOpen to a 20-min call and I can share a quick teardown + recommended enforcement workflow? Worth a look / Not a priority?\n\nRegards,\n[My Name]',
    },
  },
  {
    id: 'c_suite_sniper',
    strategy_id: 'c_suite_sniper',
    name: 'C-Suite Sniper',
    frequency: 'Executive',
    eqVibe: 'Executive / Minimal',
    vibe: 'Three sentences max with executive framing.',
    sliders: { formal: 70, outcome: 80, long: 10, diplomatic: 35 },
    whyItWorks:
      'It respects executive attention span while making a clear operating and risk argument.',
    sampleEmail: {
      subject: 'Brief risk note for leadership',
      body:
        'Hi [Name],\n\nWhen enforcement workflows lag, brand risk and team cost both rise.\n\nWe help teams tighten triage and escalation so action is faster and easier to govern.\n\nOpen to a 15-min call for a quick teardown + first automation recommendation? Worth a look / Not a priority?\n\nBest,\n[My Name]',
    },
  },
];

