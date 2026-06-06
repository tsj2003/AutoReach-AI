# AutoReach Platform Thesis

> Captured at the moment of pivot. Source of truth for "what are we building and why."

## One-line thesis

**AutoReach is an AI agent execution platform.** The first product on top of it is **outbound-as-a-service** (OaaS), priced per booked qualified meeting. The OaaS business funds and hardens the platform under real production load. In 12–18 months, the platform opens to other AI startups as a developer-tools play.

## Two products, one engine

```
              ┌───────────────────────────────────────────────┐
              │            The AutoReach Engine               │
              │                                                │
              │  Agents · Jobs · State machines · Adapters    │
              │  Observability · Cost ledger · HITL hooks     │
              │  Deliverability · Retries · Rate-limit policy │
              └───────────────────────────────────────────────┘
                            ▲                ▲
                            │                │
       Product 1 (now):     │                │   Product 2 (12–18 mo):
       Outbound-as-a-Service│                │   Public platform / SDK
       $500 per qualified   │                │   Sold to AI startups
       meeting              │                │   building agents
```

- **Product 1 (OaaS, now)**: We operate the engine on customers' behalf. They give us an offer + a calendar. We deliver booked meetings. Outcome-priced. Cash-flow positive from customer #1.
- **Product 2 (Platform, later)**: We open the engine as APIs / SDK / managed runtime for other developers building AI agents. Picks-and-shovels for the agent economy.

## Why two products

Selling infrastructure to developers without proof of scale is impossible. Selling outcomes to operators without infrastructure is brittle. By running OaaS internally, we:

- Build real revenue without a fundraise
- Battle-test the engine on production load
- Discover the right abstractions empirically (not by speculation)
- Earn the right to call it a platform when we open it up

Stripe started by processing the founders' own customers. Twilio started with its own SMS app. Temporal started inside Uber. This is the proven path.

## Core abstractions (the platform contract)

These are the primitives the engine exposes, regardless of which product is on top:

| Primitive | What it represents |
|---|---|
| **Engagement** | A long-running customer commitment: an offer, an ICP, a calendar, a goal (e.g., "20 booked meetings/month"). |
| **Agent** | An autonomous worker assigned to an Engagement. Plans, decides, acts. |
| **Job** | A discrete unit of work the Agent dispatches (e.g., "send first-touch email to prospect X"). |
| **Adapter** | A channel-specific executor: Email/Gmail, Calendar/Cal.com, eventually LinkedIn, voice, SMS. |
| **State machine** | The lifecycle of a Job: pending → running → sent → awaiting_reply → replied → booked → completed (or failed). |
| **Event** | An immutable record of something that happened (email sent, reply received, meeting booked). The audit log. |
| **Cost ledger** | Per-Engagement tracking of LLM tokens, sends, compute. Margin enforcement. |
| **HITL gate** | Human-in-the-loop checkpoint before risky actions (especially in the first 50 actions per customer — the trust ramp). |
| **Policy** | Rules: rate limits, sending windows, blocklists, deliverability thresholds, content guardrails. |

These primitives are **deliberately product-agnostic**. They work for outbound today and for any AI agent doing real-world actions tomorrow.

## Non-goals (so we don't drift)

- We are **not** building a SaaS UI for OaaS. The first version is operated by us via an internal cockpit. Customers see results, not a dashboard.
- We are **not** building the public platform yet. Every architectural decision in months 1–12 must serve OaaS first; platform-readiness is a beneficial side effect, not the goal.
- We are **not** competing with Outreach.io or Apollo on features. Different category. Different pricing model.
- We are **not** building a generic LLM framework. We are building a *runtime* for agents that do real-world actions reliably.

## The wedge that justifies $10B

Anyone can prompt an LLM to act as an agent. **Almost nobody can run thousands of agents reliably in production.** The hard problems — rate limiting, retries, deliverability, observability, cost control, HITL, multi-tenant isolation, audit trails — are exactly where "vibes-based" AI startups break down at scale. The 50–70% AI SDR churn benchmark is downstream of this.

We build the boring, hard, compounding parts. Outbound is just the first proof.

## What success looks like

| Horizon | OaaS milestone | Platform milestone |
|---|---|---|
| Month 1 | First paying customer, 5 booked meetings | Engine abstractions defined |
| Month 3 | 5 customers, $15k MRR | Adapter SDK frozen v0.1 |
| Month 6 | 20 customers, $80k MRR | Internal observability + cost ledger live |
| Month 12 | 50 customers, $250k MRR | Private alpha SDK shipped to 5 design partners |
| Month 18 | OaaS optional, platform launched | Public SDK + docs + first 100 self-serve devs |
| Month 36 | Platform is primary revenue | Series A on platform metrics |

---

## Architectural constraint — Reverse-Engineered Targeting (locked in May 2026)

**Binding for any audit / personalization / agent layer that influences who we contact and what we say.**

### The rule

The audit engine and personalization layer **never** operate on a generic "find technical pain" basis. Every signal we surface and every email we send must trace back to:

1. A specific *cure* the operating client (the OaaS customer) sells, AND
2. A *recency trigger* showing the prospect is feeling that pain right now.

Either gate failing, the prospect is dropped. No exceptions.

### Required pipeline (in order, strict)

1. **Client Cure (input)** — for every Engagement, we capture in structured form: what specific technical problem does this client's product solve? Examples:
   - "Reduces ClickHouse merge-tree write amplification at high cardinality."
   - "Auto-tunes Postgres connection pools for serverless apps."
   - "Replaces hand-rolled Celery dead-letter handling."

2. **Signal Matrix (translation)** — we translate the cure into a closed set of detectable digital footprints. Each cure has a matrix of (stack signal × hiring signal × telemetry signal × intent signal). Concretely:
   - *Stack*: BuiltWith / Wappalyzer hits, OSS PRs touching specific libraries
   - *Hiring*: job postings naming specific tech + specific pain words
   - *Telemetry*: status-page incident history, public Lighthouse drops, exposed metrics
   - *Intent*: funding events, exec hires, public roadmap statements

3. **Targeted Scan (filter)** — when scanning a prospect, the engine **ignores** signals outside the configured matrix. We do not surface generic security flaws, generic frontend issues, generic CSS, etc. *even if found.* A finding that doesn't map to the client's cure is suppressed.

4. **Trigger Gate (commerce filter)** — beyond cure-matching, the prospect must show *recency* signal that they're feeling the pain right now. A company that *might* hit this pain someday is not a target. A company that posted "Senior platform engineer to fix our Kafka cost problem" 14 days ago is. Without an active trigger inside the last 60 days, the lead is rejected.

5. **Personalization (output)** — only after all four gates pass, the email is composed referring to the *specific* matched signal, never the cure-in-the-abstract.

### Concrete consequences

- **Engagement schema must include `client_cure: str` and `signal_matrix: structured`.** A faked or generic cure will degrade the whole pipeline. We will refuse to ingest prospects until the cure is filled.
- **The audit adapter is not free-form.** It runs the cure's matrix or it doesn't run.
- **The cockpit shows the matched signal next to every email draft.** If the operator can't see "matched: Kafka in job posting + ClickHouse in OSS PRs" in the UI, the email doesn't go.
- **Negative training is recorded.** When a prospect replies "we don't have that problem," we record the signals that produced the false positive, and use them to tighten the matrix for that cure.

### What this rules out

- Audit engines that scan a wide surface and "find anything interesting." Banned.
- Personalization that uses prospect data the cure didn't justify ("I see you raised Series B — congrats!"). Banned.
- Cross-customer signal sharing without a cure-match. Banned.
- Operating without a client cure on file. Engagement creation will be blocked at the schema level when this is implemented.

### Phase placement

This is **Phase 6 architecture** (audit engine + intent matching). Phases 3–5 (Gmail send, reply detection, hardening) operate cure-blind because they are pure execution infrastructure. The rule binds the moment we add an "audit prospect" or "score prospect" or "AI-personalize from research" Job kind — and they will not be added until this constraint has a concrete schema and tests.

**This rule is non-negotiable.** Drift toward generic personalization is the failure mode that killed 11x. We will not repeat it.
