# Scenarios

The runs the page plays. Generated from `scenarios/scenarios.json`; edit the JSON, not this file.

Every company and posting here is fictional, written for this demo.

## Normal runs

### 1. Clean run

**What the visitor sees:** Complete posting: Claude asks for evaluate_job once, gets a rating, and finishes.

```text
Northwind Labs — AI Agent Architect
Location: Remote (US)
Compensation: $200,000–$240,000 base

Northwind Labs builds workflow software used by mid-size operations teams. We're adding agentic features across the product and need an AI Agent Architect to lead the work.

You'll design and ship agent workflows end to end: deciding what an agent should and shouldn't do, defining its tools, writing evaluation sets, and reviewing traces when it gets something wrong. You'll prototype hands-on with LLM APIs and coding agents, then work with two engineering teams to take the strongest prototypes to production.

What you'll do:
- Design agent workflows with clear tool boundaries and human-in-the-loop checkpoints
- Build working prototypes yourself before anything goes to engineering
- Own evaluation: golden sets, failure review, and the quality bar for release
- Partner with enterprise customers to understand where agents save real time

What you bring:
- 8+ years in product, with at least two shipping AI or ML features
- Hands-on experience building with LLM APIs and tool use
- Clear written communication; you document decisions

Fully remote within the US. Base salary $200,000–$240,000 plus equity.
```

**Expected tools:** evaluate_job

**Expected outcome:** STRONG: remote, base above $180K, and the role is hands-on agent building.

### 2. Missing info

**What the visitor sees:** No compensation anywhere: Claude picks flag_for_review instead of evaluate_job.

```text
Wrenfield Health — Senior Product Manager, Clinical AI Assistants
Location: Remote (US)

Wrenfield Health makes scheduling and intake software for outpatient clinics. We're building AI assistants that help front-desk staff handle patient intake, insurance questions, and appointment changes.

As Senior PM for Clinical AI Assistants, you'll own the assistant experience from first prototype to rollout across our clinic network. You'll work closely with clinicians and compliance to decide where an assistant can act on its own and where a person must approve.

What you'll do:
- Define the assistant's tasks, tools, and escalation rules
- Prototype new flows hands-on and test them with clinic staff
- Set up evaluation and review of assistant conversations
- Track adoption and time saved per clinic

What you bring:
- 6+ years in product management, including AI or automation products
- Comfort building prototypes with LLM APIs
- Experience in healthcare or another regulated industry

This is a fully remote role open to candidates anywhere in the US. Competitive salary and benefits.
```

**Expected tools:** flag_for_review

**Expected outcome:** Flagged for review: compensation is not listed.

### 3. Multi-tool

**What the visitor sees:** No compensation listed, so Claude researches the company first, then rates the job using what it found.

```text
Marrowstone Logistics — Principal Product Manager, Agentic Operations
Location: Remote (US)

Marrowstone Logistics runs freight brokerage and carrier operations for regional shippers. Our operations team handles thousands of load updates, carrier emails, and billing exceptions every day, and we're building agents to take on the repetitive work.

As Principal PM for Agentic Operations, you'll decide which operations tasks agents should own, design how they hand off to people, and build the first versions yourself before scaling them with engineering.

What you'll do:
- Map operations workflows and pick the highest-value tasks for agents
- Prototype agents hands-on: tools, prompts, structured outputs, retries
- Define autonomy levels and approval rules with operations leaders
- Build evaluation and monitoring so the team can trust agent output

What you bring:
- 10+ years in product, including hands-on AI or automation work
- Experience shipping agents or LLM features to real users
- Comfort reading traces and diagnosing failures

Remote within the US, with occasional visits to our operations centers.
```

**Stored company facts:**

- Company: Marrowstone Logistics
- Size: About 600 employees
- Stage: Series C, profitable operations business
- Typical base for level: $200,000–$235,000 base for Principal Product Manager
- Source note: Stored demo data, written for this scenario. Not a real company.

**Expected tools:** research_company, evaluate_job

**Expected outcome:** STRONG: research shows a $200K–$235K base for this level; remote; hands-on agent building.

### 4. Two tools at once

**What the visitor sees:** Two postings at once: Claude asks for evaluate_job and flag_for_review in the same reply, and both results go back together.

**Posting 1:**

```text
Quillmark Learning — Director of AI Product
Location: Remote (US)
Compensation: $190,000–$220,000 base

Quillmark Learning builds tutoring software used by community colleges. We're looking for a Director of AI Product to lead our AI tutor and grading assistant.

You'll set product direction for both assistants, prototype new features hands-on with LLM APIs, and work with faculty to define where AI helps students and where an instructor must stay in the loop. You'll lead a small team of two PMs and partner closely with engineering and learning science.

What you bring:
- 8+ years in product, including AI products shipped to real users
- Hands-on prototyping with LLM APIs
- Experience leading product managers

Fully remote in the US. Base salary $190,000–$220,000 plus bonus.
```

**Posting 2:**

```text
Fernhollow Insurance — Lead Product Manager, AI Claims
Location: Remote (US)

Fernhollow Insurance is modernizing claims handling for small-business policies. We're hiring a Lead PM to own AI-assisted claims intake: reading submitted documents, pulling out the key details, and routing each claim to the right adjuster.

You'll prototype extraction and routing flows, define accuracy targets with the claims team, and decide where a person must review before a claim moves forward.

What you bring:
- 7+ years in product, including document AI or automation
- Hands-on experience with LLM APIs
- Insurance or financial services background preferred

Remote within the US. Salary and benefits discussed during interviews.
```

**Expected tools:** evaluate_job, flag_for_review

**Expected outcome:** Quillmark rated STRONG; Fernhollow flagged because compensation is not listed. Both tool results go back in one message.

### 5. Hard screen in code

**What the visitor sees:** Base pay is below the floor, so a rule in code rejects the posting before Claude is ever asked.

```text
Tallowmere Robotics — AI Product Manager
Location: Remote (US)
Compensation: $140,000–$165,000 base

Tallowmere Robotics makes inspection robots for warehouses and distribution centers. We're adding AI features that let site managers ask questions about inspection results in plain language and get suggested maintenance actions.

As AI Product Manager, you'll own the natural-language assistant from prototype to launch. You'll work with our robotics and data teams to decide what the assistant can answer, how it explains its sources, and when it should hand off to a technician.

What you'll do:
- Define assistant use cases with site managers
- Prototype question-answering flows with LLM APIs
- Set accuracy targets and run evaluation before each release

What you bring:
- 5+ years in product management
- Hands-on experience with LLM APIs or search products
- Interest in industrial or hardware products

Fully remote in the US. Base salary $140,000–$165,000 plus equity.
```

**Expected tools:** none (no tool runs)

**Expected outcome:** Rejected by a hard screen in code: base pay is below the $180K floor. No API call is made.

## Break the agent (fault injected on purpose, labeled on the page)

### 6. A tool fails

**What the visitor sees:** The grader inside evaluate_job returns broken JSON (injected). The error goes back to Claude, which decides how to recover.

**Injected fault:** `tool_fails`

```text
Veltrane Software — Staff Product Manager, AI Platform
Location: Remote (US)
Compensation: $205,000–$240,000 base

Veltrane Software makes developer tools for data teams. Our AI platform group builds the shared services every product team uses to ship AI features: model routing, evaluation, prompt management, and tracing.

As Staff PM for the AI Platform, you'll own the roadmap for those shared services and treat internal product teams as your customers. You'll prototype new platform capabilities hands-on and measure success by how quickly teams ship reliable AI features.

What you'll do:
- Turn one-off AI integrations into reusable platform services
- Prototype platform features yourself with LLM APIs
- Define quality and cost metrics for AI features across the company
- Run design reviews with engineering leads

What you bring:
- 9+ years in product, including platform or developer products
- Hands-on experience building with LLM APIs
- Comfort with APIs, observability, and cost tradeoffs

Remote within the US. Base salary $205,000–$240,000 plus equity.
```

**Expected tools:** evaluate_job

**Expected outcome:** evaluate_job fails (injected broken JSON); the error goes to Claude marked is_error; Claude retries or explains the failure; the run still finishes.

### 7. Unknown tool

**What the visitor sees:** Claude's tool request names a tool that doesn't exist (injected). Python replies with an error listing the real tools.

**Injected fault:** `unknown_tool`

```text
Corvalis Payments — Principal Product Manager, Applied AI
Location: Remote (US)
Compensation: $210,000–$245,000 base

Corvalis Payments processes payments for small online merchants. Our Applied AI team builds features that cut merchants' busywork: dispute responses, payout questions, and fraud review notes.

As Principal PM for Applied AI, you'll find the merchant tasks where AI saves the most time, build working prototypes yourself, and lead them through launch with engineering and risk.

What you'll do:
- Prototype AI features hands-on with LLM APIs and tool use
- Define evaluation sets and release criteria with the risk team
- Decide where AI drafts and where a person must approve
- Measure time saved per merchant

What you bring:
- 10+ years in product, with AI features shipped to paying customers
- Hands-on building experience
- Payments or fintech experience preferred

Remote within the US. Base salary $210,000–$245,000 plus equity.
```

**Expected tools:** (unknown tool, injected), evaluate_job

**Expected outcome:** Python returns an is_error result naming the real tools; Claude then calls evaluate_job and the posting rates STRONG.

### 8. Runaway loop stopped

**What the visitor sees:** The tool fails on every attempt (injected). Claude retries; the loop cap, lowered to 2 passes for this demo (injected), stops the run.

**Injected fault:** `runaway_loop`

```text
Lumen & Pine Media — Senior Product Manager, Generative AI Tools
Location: Remote (US)
Compensation: $185,000–$215,000 base

Lumen & Pine Media publishes regional news and lifestyle sites. Our newsroom tools team builds software for editors and reporters, and we're adding AI tools for headline testing, summaries, and research help.

As Senior PM for Generative AI Tools, you'll work with editors to decide where AI helps and where it doesn't belong, prototype tools hands-on, and set clear rules for review before anything is published.

What you'll do:
- Prototype editorial AI tools with LLM APIs
- Define review rules so nothing AI-written publishes unchecked
- Run evaluation on summaries and headline suggestions
- Train newsroom staff on the tools you ship

What you bring:
- 6+ years in product management, including AI or content tools
- Hands-on prototyping experience
- Respect for editorial standards

Remote within the US. Base salary $185,000–$215,000.
```

**Expected tools:** evaluate_job (repeated, always fails)

**Expected outcome:** Every attempt fails; the run stops at the lowered cap of 2 passes and returns "Stopped after 2 passes without finishing." (Real Claude retries a failing tool once and then stops on its own, so the cap is lowered for this fault; see #46.)

### 9. Reply cut off

**What the visitor sees:** Claude's reply runs out of room (injected low token limit). The cut-off is detected and the run stops with a clear message.

**Injected fault:** `reply_cut_off`

```text
Tidewick Civic Tech — Head of AI Product
Location: Remote (US)
Compensation: $220,000–$260,000 base

Tidewick Civic Tech builds software that state and local governments use to run public services: permit applications, benefits enrollment, and resident support lines. Our products are used by more than 200 agencies, and most of the people they serve are trying to get something done quickly, often on a phone, often in a second language.

We're hiring our first Head of AI Product to lead how AI shows up across our products. The work starts with resident support: an assistant that answers questions about permits and benefits, helps people fill out forms correctly, and hands off to agency staff when a question needs a person. It extends to tools for agency staff: summarizing case histories, drafting responses, and finding the right policy section in long regulations.

This is a hands-on leadership role. You'll build early prototypes yourself, then lead a team of three product managers and work closely with engineering, design, accessibility, and our public-sector policy team. Government work raises the bar on trust: answers must cite the policy they come from, every automated action must be logged, and residents must always be able to reach a person.

What you'll do:
- Set the AI product strategy across resident and staff products
- Prototype assistants hands-on with LLM APIs, tool use, and retrieval
- Define when the assistant answers, when it asks, and when it hands off
- Build evaluation and review processes that agency partners can audit
- Make accessibility and plain language requirements, not afterthoughts
- Lead and grow a team of product managers
- Represent the product with agency leaders and procurement teams

What you bring:
- 10+ years in product, including AI products shipped to real users
- Hands-on experience building with LLM APIs, including retrieval and tool use
- Experience leading product managers
- Comfort working in regulated or public-sector environments
- Clear writing; you can explain an AI system's limits to a non-technical audience

We're fully remote within the US, with travel two to four times a year to meet agency partners. Base salary $220,000–$260,000 plus benefits.
```

**Expected tools:** none (no tool runs)

**Expected outcome:** The reply is cut off by the injected token limit; the run stops with "Claude's reply was cut off (hit the max_tokens limit of …)."
