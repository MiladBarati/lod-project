import sys
from typing import Dict, Any

try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """
    Estimates or counts the number of tokens in a string using tiktoken.
    Falls back to a character ratio if tiktoken is not installed.
    """
    if HAS_TIKTOKEN:
        try:
            encoding = tiktoken.get_encoding(encoding_name)
            return len(encoding.encode(text))
        except Exception:
            pass
    # Fallback: ~3.8 characters per token is a solid heuristic for code/JSON/markdown
    return max(1, int(len(text) / 3.8))

def generate_benchmark_report(raw_json: str, human_md: str, lom_text: str) -> str:
    """
    Computes size differences, token compression ratios, and estimated
    costs, returning a formatted printable string.
    """
    raw_tokens = count_tokens(raw_json)
    human_tokens = count_tokens(human_md)
    lom_tokens = count_tokens(lom_text)
    
    raw_chars = len(raw_json)
    human_chars = len(human_md)
    lom_chars = len(lom_text)
    
    savings_vs_json = (1 - (lom_tokens / raw_tokens)) * 100 if raw_tokens else 0
    savings_vs_human = (1 - (lom_tokens / human_tokens)) * 100 if human_tokens else 0
    
    # Assume GPT-4o input tokens pricing: $2.50 per 1 Million tokens
    cost_per_m = 2.50
    cost_json = (raw_tokens * cost_per_m) / 1_000
    cost_human = (human_tokens * cost_per_m) / 1_000
    cost_lom = (lom_tokens * cost_per_m) / 1_000
    
    saved_cost_vs_json = cost_json - cost_lom
    saved_cost_vs_human = cost_human - cost_lom
    
    report = []
    report.append("=" * 72)
    report.append("             TOKEN & COST COMPRESSION BENCHMARK REPORT             ")
    report.append("=" * 72)
    
    report.append(f" Format        │ Size (Chars) │ Token Count (cl100k) │ Cost / 1M Requests")
    report.append(f"───────────────┼──────────────┼──────────────────────┼───────────────────")
    report.append(f" Raw JSON      │ {raw_chars:<12,d} │ {raw_tokens:<20,d} │ ${cost_json:,.2f}")
    report.append(f" Standard MD   │ {human_chars:<12,d} │ {human_tokens:<20,d} │ ${cost_human:,.2f}")
    report.append(f" LOM (LLM Opt) │ {lom_chars:<12,d} │ {lom_tokens:<20,d} │ ${cost_lom:,.2f}")
    report.append(f"───────────────┴──────────────┴──────────────────────┴───────────────────")
    
    report.append(f"\nCOMPRESSION METRICS:")
    report.append(f"  • Token Savings vs. Raw JSON:  {savings_vs_json:.1f}%")
    report.append(f"  • Token Savings vs. Human MD:  {savings_vs_human:.1f}%")
    report.append(f"  • Financial Savings (vs JSON): ${saved_cost_vs_json:,.2f} per 1M queries")
    report.append(f"  • Financial Savings (vs Hum):  ${saved_cost_vs_human:,.2f} per 1M queries")
    report.append("=" * 72)
    
    return "\n".join(report)
