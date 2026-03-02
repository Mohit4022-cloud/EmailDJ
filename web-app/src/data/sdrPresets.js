export const SDR_PRESETS = [
  {
    id: 1,
    name: 'The Straight Shooter',
    frequency: 'High Volume Daily Use',
    eqVibe: 'Top 40 / Pop-Rock',
    vibe:
      'Clear, concise, and purely functional. Used for standard, high-volume persona-based campaigns...',
    sliders: { formal: 60, outcome: 50, long: 40, diplomatic: 40 },
    whyItWorks: 'In a world of overly clever emails, clarity wins.',
    sampleEmail: {
      subject: 'Quick question about your outbound workflow',
      body:
        'Hi [Name],\n\nNoticed your team is scaling up SDRs this quarter. We help outbound teams increase reply rates by 20% by automating preset drafting.\n\nAre you open to a quick chat to see if this aligns with your Q3 goals?\n\nBest,\n[My Name]',
    },
  },
  {
    id: 2,
    name: 'The Headliner',
    frequency: 'High Volume Daily Use',
    eqVibe: 'Stadium Anthem / High Energy',
    vibe: "FOMO-driven and metric-heavy. The 'Social Proof' play.",
    sliders: { formal: 40, outcome: 90, long: 60, diplomatic: 20 },
    whyItWorks:
      "Buyers are competitive. If a VP hears that a rival just increased revenue by 12%...",
    sampleEmail: {
      subject: 'How [Competitor] increased revenue 12%',
      body:
        'Hi [Name],\n\nJust helped [Direct Competitor] achieve a 12% bump in outbound pipeline using our Remix Studio. We bypassed the usual spam filters and got them straight to the decision-maker.\n\nWorth a 10-minute look to see how they did it?\n\nCheers,\n[My Name]',
    },
  },
  {
    id: 3,
    name: 'The Giver',
    frequency: 'Medium-High Volume',
    eqVibe: 'Lo-Fi / Chill Beats',
    vibe:
      "Helpful, zero-pressure, and value-first. The 'Deposit before Withdrawal' play.",
    sliders: { formal: 20, outcome: 40, long: 30, diplomatic: 100 },
    whyItWorks:
      "It dramatically lowers the barrier to entry. Harder to say 'no' to a free resource...",
    sampleEmail: {
      subject: 'Made a quick video audit for your site',
      body:
        'Hi [Name],\n\nNoticed a tiny gap in your current email sequencing on the site. I recorded a 2-minute Loom breaking down exactly how to fix it to capture more leads.\n\nMind if I send the link over? No worries if not.\n\nThanks,\n[My Name]',
    },
  },
  {
    id: 4,
    name: 'The Challenger',
    frequency: 'Medium Volume',
    eqVibe: 'High Distortion / Rock',
    vibe:
      "Disruptive and provocative. Challenges a status quo belief to create urgency around a hidden risk.",
    sliders: { formal: 40, outcome: 0, long: 40, diplomatic: 0 },
    whyItWorks:
      'It reframes inertia as a business cost, which forces the buyer to reassess today.',
    sampleEmail: {
      subject: 'A risk your outbound team may not see yet',
      body:
        "Hi [Name],\n\nA pattern we keep seeing: teams optimize send volume while reply quality quietly drops quarter over quarter.\n\nIf that trend is showing up at [Company], I can share the exact signal framework teams use to catch it early.\n\nOpen to a quick compare next week?\n\nBest,\n[My Name]",
    },
  },
  {
    id: 5,
    name: 'The Industry Insider',
    frequency: 'Medium Volume, Trigger-Based',
    eqVibe: 'Spoken Word / Podcast',
    vibe:
      'Insight-led and research-heavy. Connects a recent market or company trigger to a practical next move.',
    sliders: { formal: 50, outcome: 40, long: 75, diplomatic: 85 },
    whyItWorks:
      'It earns attention by teaching first, then positioning the offer as a logical extension.',
    sampleEmail: {
      subject: 'One takeaway from your latest earnings call',
      body:
        "Hi [Name],\n\nAfter reading your latest update on pipeline efficiency, one risk stood out: reps are personalizing later in the cycle instead of first touch.\n\nWe built a lightweight preset workflow that fixes that without changing your stack.\n\nHappy to share a 2-page breakdown if useful.\n\nRegards,\n[My Name]",
    },
  },
  {
    id: 6,
    name: 'The Icebreaker',
    frequency: 'Medium-Low Volume, Trigger-Based',
    eqVibe: 'Pop / Upbeat & Light',
    vibe:
      'Warm and conversational with a low-friction opener, designed for warm outbound or shared context.',
    sliders: { formal: 0, outcome: 70, long: 30, diplomatic: 70 },
    whyItWorks:
      'It feels human and specific, reducing resistance from prospects who ignore generic outreach.',
    sampleEmail: {
      subject: 'Small idea after your team update',
      body:
        "Hi [Name],\n\nSaw your post about expanding the SDR team, congrats on the momentum.\n\nIf helpful, I can share a simple preset workflow we use to keep personalization quality high while volume scales.\n\nWant me to send it over?\n\nCheers,\n[My Name]",
    },
  },
  {
    id: 7,
    name: 'The Trusted Advisor',
    frequency: 'Low Volume, Persona-Specific',
    eqVibe: 'Classical / Balanced Theater',
    vibe:
      'Consultative and thorough. Adds enough detail for operators who need confidence before a meeting.',
    sliders: { formal: 80, outcome: 50, long: 80, diplomatic: 90 },
    whyItWorks:
      'It gives mid-level decision-makers language and proof points they can take internally.',
    sampleEmail: {
      subject: 'Framework to improve SDR reply quality safely',
      body:
        "Hi [Name],\n\nMost teams we work with want better reply rates but need to avoid risky messaging changes.\n\nWe use a controlled preset framework: lock factual anchors, let reps tune tone in bounds, and review deltas before rollout.\n\nIf useful, I can share the exact rollout checklist.\n\nBest,\n[My Name]",
    },
  },
  {
    id: 8,
    name: 'The C-Suite Sniper',
    frequency: 'Low Volume, Persona-Specific',
    eqVibe: 'Bass-Heavy & Punchy',
    vibe:
      'Executive-first and direct. Focuses on strategic impact, not features.',
    sliders: { formal: 70, outcome: 80, long: 0, diplomatic: 20 },
    whyItWorks:
      'Senior leaders skim quickly; this format makes the business case in seconds.',
    sampleEmail: {
      subject: 'Reducing outbound waste this quarter',
      body:
        "Hi [Name],\n\nLeaders are spending more on outbound while conversion quality stays flat.\n\nWe help teams increase qualified replies without adding headcount by enforcing message discipline at draft time.\n\nWorth 12 minutes to assess fit?\n\nBest,\n[My Name]",
    },
  },
  {
    id: 9,
    name: 'The Visionary',
    frequency: 'Situational, Strategic',
    eqVibe: 'Orchestral / Cinematic',
    vibe:
      'Narrative-driven and future-oriented. Frames a larger shift and invites the buyer into it.',
    sliders: { formal: 50, outcome: 100, long: 90, diplomatic: 50 },
    whyItWorks:
      'Useful for category-creating products where belief in a new approach matters more than features.',
    sampleEmail: {
      subject: 'What outbound looks like in the next 12 months',
      body:
        "Hi [Name],\n\nOutbound is moving from template execution to adaptive, account-aware drafting.\n\nTeams that adopt this shift now are creating compounding advantages in reply quality and speed to pipeline.\n\nIf you are exploring that direction, I can share how leading SDR orgs are implementing it.\n\nRegards,\n[My Name]",
    },
  },
  {
    id: 10,
    name: 'The VIP Pass',
    frequency: 'Situational, Highly Targeted',
    eqVibe: 'Jazz / Smooth & Coordinated',
    vibe:
      'Contextual and deferential. Best for referral-led or multi-threaded outreach with internal context.',
    sliders: { formal: 80, outcome: 70, long: 20, diplomatic: 90 },
    whyItWorks:
      'Borrowed trust shortens the path to a response when handled with precision and restraint.',
    sampleEmail: {
      subject: 'Following up from [Mutual Contact]',
      body:
        "Hi [Name],\n\n[Mutual Contact] suggested I reach out given your current focus on pipeline quality.\n\nWe have helped teams in a similar motion tighten first-touch messaging without adding operational overhead.\n\nIf useful, happy to share a brief summary and let you decide if a call makes sense.\n\nBest,\n[My Name]",
    },
  },
];

