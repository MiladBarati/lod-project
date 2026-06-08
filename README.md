# LOD — LLM-Optimized Documentation

API schema governance and runtime self-healing guardrails for LLM agent pipelines.

[![PyPI Version](https://img.shields.io/pypi/v/lod-cli.svg)](https://pypi.org/project/lod-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

```bash
pip install lod-cli
```

---

## What is LOD?

LOD is developer infrastructure that prevents LLM agent failures caused by undetected API schema drift and model hallucinations. It acts as a contract safety layer for your LLM agents at both **build-time** (CI/CD) and **runtime** (validation proxy).

---

## 30-Second Quick Start

### 1. Compile OpenAPI Spec to Token-Optimized Prompt Specs
Reduce prompt token size and improve model comprehension by converting raw OpenAPI JSON/YAML to LLM-friendly schemas:
```bash
lod compile -i openapi.json -o api-prompt-spec.xml --model claude
```

### 2. Detect Breaking API Schema Drift in CI/CD
Fail builds when upstream APIs make breaking changes that downstream LLMs can't handle:
```bash
lod check -i openapi.json -b baseline-openapi.json
```

### 3. Intercept & Self-Heal Hallucinated Payloads at Runtime
Run the local validation proxy to intercept outbound agent API calls, validate contracts, and return structured self-healing feedback to the model:
```bash
lod proxy --port 8080 --spec openapi.json --target-url https://api.production.com
```

---

## Core Capabilities

| Capability | Phase | CLI Command / SDK | Description |
|---|---|---|---|
| **LLM Compilation** | Build | `lod compile` | OpenAPI spec to XML (Claude), YAML (GPT), or TypeScript (Gemini) prompt specs. |
| **Drift Detection** | CI/CD | `lod check` | Structural diff of specs to identify breaking vs. non-breaking changes. |
| **Auto-Remediation** | CI/CD | `lod remediate` | Re-compiles specs, commits to a branch, and opens a GitHub PR automatically. |
| **Remediation Verification**| CI/CD | `lod remediate --verify-cmd` | Runs local integration/eval tests to verify the re-compiled spec. |
| **Validation Proxy** | Runtime | `lod proxy` | Reverse proxy intercepting requests, validating schemas, returning `422` correction templates. |
| **Client Middleware** | Runtime | `lod.middleware` | Low-latency in-process validation wrappers for `requests` and `httpx`. |
| **Token Benchmarking** | Dev | `lod benchmark` | Quantify token size and dollar savings of compiled formats vs. raw specs. |
| **Spec Registry** | Dev | `lod registry` | Local versioned baseline registry (`registry://api:v1.0.0`) for quick diffing. |

---

## Supported LLM Output Formats

Optimize your prompts depending on the target LLM. Different models perform best with different serialization styles:

| Model / Target | Output Format | CLI Flag | Best Used For |
|---|---|---|---|
| **Claude** (Anthropic) | XML tags | `--model claude` | Best for Claude 3/3.5 prompt context structure. |
| **GPT** (OpenAI) | Whitespace-optimized YAML | `--model gpt` | Clean, low-token representation for GPT-4/4o. |
| **Gemini** (Google) | TypeScript Interfaces | `--model gemini` | Highly typed JSON-like comprehension for Gemini Pro/Flash. |
| **Default** (Generic) | YAML-like LOM | (none) | General-purpose LLM-Optimized Markdown. |

---

## Runtime Self-Healing Example

When your agent generates a payload with a missing field or wrong type, the LOD validation proxy/middleware intercepts the call and replies with a structured error:

```json
{
  "error": "LOD Schema Validation Failed",
  "status": 422,
  "details": {
    "missing_properties": ["user_id"],
    "invalid_types": {
      "age": {
        "expected": "integer",
        "received": "string"
      }
    }
  }
}
```

Your agent loop catches this `422`, feeds it back into the LLM context, and automatically regenerates a corrected payload on the retry loop.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
