# LOD — Business Plan

**LLM-Optimized Documentation: API Schema Governance for LLM Pipelines**

---

## 1. Executive Summary

LOD is a developer infrastructure tool that prevents LLM agent failures caused by undetected API schema changes and model hallucination. It acts as a safety layer in both the CI/CD pipeline and the active runtime environment, detecting breaking schema drift, compiling context-optimized prompts for Claude/GPT/Gemini, and executing real-time interception and self-healing validation on outbound agent requests.

**The problem is simple:** When an API team ships a breaking change, or when an LLM non-deterministically hallucinates a payload, downstream LLM agents break silently. Traditional API gateways reject these calls, crashing the agent and causing immediate production downtime.

**LOD solves it in four commands:**
- `lod check` — detect breaking drift between API spec versions during CI/CD
- `lod compile` — produce token-optimized API specs for LLM context windows
- `lod proxy` — run the runtime validation proxy to intercept and self-heal outbound agent requests
- `lod remediate` — verify and auto-fix broken LLM prompt specs via GitHub PR

---

## 2. Problem

### The Pain

Every company building LLM-powered products faces a critical runtime vulnerability:

1. **API team ships a change** — renames a field, removes an endpoint, changes a parameter from optional to required.
2. **LLM output drifts** — even without code changes, updates to model weights or temperature variations cause the agent to generate malformed payloads.
3. **LLM agents fail silently** — they call nonexistent endpoints or send corrupted requests, resulting in broken customer workflows.
4. **Outages cost cash** — engineering teams waste hours in cross-team forensics trying to debug why an autonomous agent suddenly stopped completing tasks.

This problem scales exponentially as organizations transition from simple chatbots to autonomous agent fleets consuming dozens of internal and external APIs.

### Why Now

- **Agentic AI adoption is accelerating** — Agents executing real-world API actions require strict contract enforcement; a single malformed payload can execute a garbage transaction.
- **Shift-Left and Shield-Right are standard** — Teams want build-time checks in CI/CD *and* dynamic guardrails in production.
- **Context window costs are collapsing, but correctness is not** — While token prices are dropping to zero, the cost of agent transaction failures and system downtime remains astronomical. LOD focuses on correctness first.

---

## 3. Solution

### Product Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                           LOD System                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Build Time]                                                    │
│   OpenAPI Spec ──► lod compile ──► LLM-Optimized Format          │
│        │                                                         │
│        ▼                                                         │
│   lod check ──► Drift Report ──► Breaking? ──┐                   │
│        │                                      │                  │
│        ▼                                      ▼                  │
│   lod registry                        lod remediate ──► Open PR  │
│                                                                  │
│  [Runtime]                                                       │
│   LLM Agent ──► [lod proxy] ──(Valid?)──► Upstream API Target    │
│                    │                                             │
│                    └──(Invalid: 422 Error with Schema Feedback)──┘
│                        │                                         │
│                        └──► LLM Self-Heals Request & Retries     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Current Capabilities (Shipped)

| Capability | Status | Description |
|---|---|---|
| **LLM Compilation** | ✅ Live | OpenAPI → token-optimized output for Claude (XML), GPT (YAML), Gemini (TypeScript) |
| **Drift Detection** | ✅ Live | Structural comparison of two OpenAPI specs — identifies breaking vs. non-breaking changes |
| **Auto-Remediation** | ✅ Live | Detects drift → recompiles LLM spec → creates GitHub branch → opens PR |
| **Remediation Verification** | ✅ Live | Overwrites local specs to run agent integration tests (`--verify-cmd`) |
| **Runtime Validation Proxy**| ✅ Live | Intercepts HTTP requests, validates them against specs, and returns structured `422` self-healing schemas |
| **In-Process Middleware** | ✅ Live | In-process validation wrappers for `requests`/`httpx` with async privacy-first telemetry reporting |
| **Token Benchmarking** | ✅ Live | Quantifies token savings and cost reduction vs. raw JSON and standard markdown |
| **Spec Registry** | ✅ Live | Local versioned storage for baseline specs (`registry://api:v1.0.0` URIs) |

---

## 4. Market

### Target Customer

**Primary ICP:** Engineering teams at Series A+ companies (50-500 engineers) that:
- Operate API-first architectures with OpenAPI specifications
- Run autonomous LLM agents that execute actions (write/mutate states) via APIs
- Require 99.9% uptime on customer-facing AI products

**Buyer:** Platform Engineering lead, Developer Experience lead, or AI/ML Engineering manager.
**User:** Backend engineers maintaining API specs + AI engineers maintaining LLM agent loops.

### Market Sizing

At a transactional and contract value matching runtime volumes, the blended ACV scales to $12,000/yr (focusing on mid-market to enterprise):

| Tier | Companies | Revenue |
|---|---|---|
| **TAM (OpenAPI + LLM intersection)** | 175,000 | $2.1B ARR |
| **SAM (5+ API consumers using LLMs)** | 26,000 | $312M ARR |
| **SOM (Year 3)** | 500 | $6M ARR |

---

## 5. Competitive Landscape

### Direct Competitors

LOD represents a category creation. While API documentation tools exist, none combine build-time schema governance with a **self-healing runtime proxy** for LLM agents.

### Adjacent Tools

- **Optic / Speakeasy:** Focuses on SDK generation and static drift. They lack runtime enforcement and LLM self-healing feedback.
- **Pydantic / Guardrails AI:** Focuses on prompt validation (regex, Pydantic coercion), but is not integrated with the enterprise source of truth—the OpenAPI spec. LOD bridges the OpenAPI spec directly to the runtime request pipeline.

---

## 6. Business Model

### Pricing Strategy

LOD utilizes a developer-first PLG CLI funnel coupled with a **usage-based runtime pricing model** for teams.

| Tier | Price | What You Get |
|---|---|---|
| **Open Source CLI** | Free | Local compilation, CLI drift checks, local registry, local in-process middleware. |
| **Team** | $250/mo + Usage | Webhook-triggered checks, Slack/email alerts, telemetry event collection, and **50,000 monitored/telemetry events/mo** (additional events at $0.05/100). |
| **Business** | $999/mo + Usage | Multi-repo support, SSO, audit logs, custom LLM templates, and **250,000 monitored/telemetry events/mo**. |
| **Enterprise** | Custom | Self-hosted registry and telemetry, SLA, unlimited events, custom integrations. |

*Rationale:* Tying pricing to monitored requests and telemetry events aligns LOD's revenue directly with the scale of the customer's active agent fleet without requiring them to route production traffic through our external proxy. As agents run more loops, our value and revenue compound.

---

## 7. Go-To-Market Strategy

### Phase 1: Developer Onboarding (Months 1-6)
- **Play:** Own the local developer workflow. Drive adoption of the free CLI for compilation and local proxy debugging.
- **Metric:** PyPI downloads, CLI proxy runs, GitHub stars.

### Phase 2: Pipeline & Runtime Protection (Months 6-12)
- **Play:** Target engineering teams running agents in production. Convince them to route outbound agent requests through LOD's proxy to eliminate silent API failures.
- **Metric:** Monitored endpoints, weekly active proxy connections.

### Phase 3: Monetization & Enterprise (Months 12-24)
- **Play:** Upsell teams on shared registry versioning, telemetry dashboards, and high-throughput proxy hosting.
- **Metric:** Net Revenue Retention (NRR) > 120%, Monthly Recurring Revenue (MRR).

---

## 8. Product Roadmap

### Near-Term (0-6 Months)
- **P0**: Publish package to PyPI (`pip install lod`).
- **P0**: Launch hosted proxy runtime for cloud agent deployments.
- **P1**: CLI `lod proxy` integration (Shipped).
- **P1**: Remote/shared spec registry.

### Mid-Term (6-12 Months)
- **P0**: Dashboard for proxy validation analytics (logging schema violation trends).
- **P1**: Integration with popular LLM orchestration frameworks (LangChain, LlamaIndex, CrewAI) as an optional middleware wrapper.
- **P2**: Custom templates for 422 self-healing payloads.

---

## 9. Financial Projections

### Revenue Forecast (Assuming 5% CLI-to-Proxy Conversion)

| Month | CLI Users | Active Proxied Repos | MRR | ARR |
|---|---|---|---|---|
| 6 | 500 | 10 | $2.5K | $30K |
| 12 | 2,000 | 80 | $22K | $264K |
| 24 | 10,000 | 450 | $125K | $1.5M |

---

## 10. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Token prices drop to zero** | Low (Impact) | We pivot completely away from "token savings" metrics. The proxy focuses on **correctness and uptime**, which remains highly valuable regardless of token pricing. |
| **Models natively handle raw API specs** | Medium | Even if LLMs read specs perfectly, they still hallucinate and backend APIs still change. The proxy is an infrastructure contract validator, not just a prompt compiler. |
| **Proxy latency overhead** | Low (Impact) | Mitigated by providing **in-process client middleware wrappers** (transports/adapters) that execute contract validation locally at microsecond speeds with asynchronous, thread/task-based telemetry queues. |
| **Proxy security & compliance blockers** | High | Mitigated by utilizing **in-process middleware SDKs with automatic privacy scrubbing** (redacting query values, deleting raw bodies/tokens), shipping only metadata validation anomalies to LOD. |

---

## 11. Success Metrics

### North Star Metric
- **Outages Prevented / Self-Healed Errors**: The number of validation failures caught by `lod proxy` and successfully corrected by the agent without human developer intervention.

---

## 12. Execution Summary

LOD's thesis is absolute: **as LLM agents become the primary consumers of APIs, active runtime schema governance and self-healing request validation are mission-critical requirements for software stability.**

By owning the local proxy during development and scaling into the production gateway layer, LOD positions itself at the high-leverage intersection of API management and AI operations. We are not selling a documentation format; we are selling system reliability.
