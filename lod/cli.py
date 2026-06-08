import argparse
import json
import os
import sys
import time
import urllib.request
from typing import Any, Dict

from .drift import compare_specs
from .registry import get_spec, register_spec, resolve_registry_uri
from .remediation import GithubRemediator

__version__ = "0.2.0"


def load_spec_from_source(source: str) -> Dict[str, Any]:
    """Loads baseline spec from local path, URL, or registry URI."""
    if source.startswith("registry://"):
        return resolve_registry_uri(source)
    elif source.startswith("http://") or source.startswith("https://"):
        try:
            req = urllib.request.Request(source, headers={'User-Agent': 'LOD-CLI/0.2.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            raise ValueError(f"Failed to fetch remote spec from URL '{source}': {e}")
    else:
        if not os.path.exists(source):
            raise FileNotFoundError(f"Baseline file '{source}' not found.")
        if os.path.isdir(source):
            raise ValueError(f"Baseline path '{source}' is a directory, not a file.")
        with open(source, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON syntax in baseline file '{source}': {e}")


def load_input_spec(input_path: str) -> tuple:
    """Loads and validates an input spec file. Returns (data, raw_json_str)."""
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(input_path):
        print(f"Error: Path '{input_path}' is a directory, not a file.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_json_str = f.read()
        data = json.loads(raw_json_str)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON syntax in file '{input_path}':", file=sys.stderr)
        print(f"  Line {e.lineno}, Column {e.colno}: {e.msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to read file '{input_path}': {e}", file=sys.stderr)
        sys.exit(1)

    return data, raw_json_str


def validate_openapi_spec(data: Any, input_path: str) -> None:
    """Validates that input data looks like an OpenAPI spec."""
    if not isinstance(data, dict) or ("openapi" not in data and "swagger" not in data):
        print(f"Error: Input file '{input_path}' does not appear to be an OpenAPI specification.", file=sys.stderr)
        print("  Expected a JSON object with an 'openapi' or 'swagger' key.", file=sys.stderr)
        sys.exit(1)


# --- Subcommand handlers ---

def cmd_compile(args: argparse.Namespace) -> None:
    """Compile an OpenAPI spec into LLM-optimized format."""
    data, _ = load_input_spec(args.input)
    validate_openapi_spec(data, args.input)

    start_time = time.perf_counter()

    try:
        from .llm_openapi import LLMOpenAPIConverter
        converter = LLMOpenAPIConverter(data, model=args.model)
        result = converter.convert()
    except Exception as e:
        print(f"Error during compilation: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = args.output
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result)
        except Exception as e:
            print(f"Error writing file '{output_path}': {e}", file=sys.stderr)
            sys.exit(1)

        duration = time.perf_counter() - start_time
        print(f"Successfully saved output to '{output_path}'.", file=sys.stderr)
        print(f"Total time elapsed: {duration:.4f} seconds.", file=sys.stderr)
    else:
        print(result)
        duration = time.perf_counter() - start_time
        print(f"Successfully compiled. Time elapsed: {duration:.4f} seconds.", file=sys.stderr)


def cmd_check(args: argparse.Namespace) -> None:
    """Check for breaking schema drift between two specs."""
    data, _ = load_input_spec(args.input)

    try:
        baseline_data = load_spec_from_source(args.baseline)
    except Exception as e:
        print(f"Error loading baseline spec: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        report = compare_specs(baseline_data, data)
    except Exception as e:
        print(f"Error performing spec comparison: {e}", file=sys.stderr)
        sys.exit(2)

    if report["is_breaking"]:
        print("CRITICAL: Breaking schema changes detected!", file=sys.stderr)
        for change in report["breaking_changes"]:
            print(f"  - BREAKING: {change}", file=sys.stderr)
        sys.exit(1)
    else:
        print("No breaking schema changes detected.")
        if report["non_breaking_changes"]:
            print("Non-breaking changes detected:")
            for change in report["non_breaking_changes"]:
                print(f"  - {change}")
        sys.exit(0)


def cmd_remediate(args: argparse.Namespace) -> None:
    """Detect breaking drift and auto-create a GitHub PR with the fix."""
    data, _ = load_input_spec(args.input)

    try:
        baseline_data = load_spec_from_source(args.baseline)
    except Exception as e:
        print(f"Error loading baseline spec: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        report = compare_specs(baseline_data, data)
    except Exception as e:
        print(f"Error performing spec comparison: {e}", file=sys.stderr)
        sys.exit(2)

    if not report["is_breaking"]:
        print("No breaking changes detected. Remediation not needed.")
        sys.exit(0)

    print("CRITICAL: Breaking schema changes detected!", file=sys.stderr)
    for change in report["breaking_changes"]:
        print(f"  - BREAKING: {change}", file=sys.stderr)

    print("Initiating automated remediation...", file=sys.stderr)

    token = args.git_token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GitHub authentication token must be provided via --git-token or GITHUB_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)

    try:
        remediator = GithubRemediator(
            repo=args.git_repo,
            token=token,
            target_file=args.target_file
        )
        rem_report = remediator.remediate(
            data,
            model=args.model,
            verify_cmd=args.verify_cmd,
            allow_failed_verification=args.allow_failed_verification
        )
        print("Remediation successful!", file=sys.stderr)
        print(f"  Branch created: {rem_report['branch']}", file=sys.stderr)
        print(f"  Pull Request opened: {rem_report['pr_url']}", file=sys.stderr)
    except ValueError as e:
        if "Verification failed" in str(e):
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(3)
        print(f"Error during remediation: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during remediation: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_benchmark(args: argparse.Namespace) -> None:
    """Generate a token footprint and cost comparison report."""
    data, raw_json_str = load_input_spec(args.input)

    try:
        from .llm_openapi import LLMOpenAPIConverter
        lom_md = LLMOpenAPIConverter(data, model=args.model).convert()

        # Generate a human-readable markdown equivalent for comparison
        # We use the generic LOM format as a baseline comparison
        human_md = LLMOpenAPIConverter(data, model=None).convert()

        from .benchmark import generate_benchmark_report
        report = generate_benchmark_report(raw_json_str, human_md, lom_md)
        print(report)
    except Exception as e:
        print(f"Error running token benchmark: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_registry(args: argparse.Namespace) -> None:
    """Registry subcommand dispatcher."""
    if args.registry_action == "register":
        try:
            dest_path = register_spec(args.input, args.spec_id, args.tag)
            print(f"Successfully registered spec '{args.spec_id}' with tag '{args.tag}' at: {dest_path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error registering spec: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.registry_action == "get":
        try:
            data = get_spec(args.spec_id, args.tag)
            parent_dir = os.path.dirname(args.output)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Successfully retrieved spec '{args.spec_id}' tag '{args.tag}' and saved to '{args.output}'")
            sys.exit(0)
        except Exception as e:
            print(f"Error retrieving spec: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: Unknown registry action. Use 'register' or 'get'.", file=sys.stderr)
        sys.exit(1)


def cmd_proxy(args: argparse.Namespace) -> None:
    """Start the dynamic request validation proxy server."""
    data, _ = load_input_spec(args.input)
    validate_openapi_spec(data, args.input)

    try:
        from .proxy import start_proxy
        start_proxy(
            spec_data=data,
            upstream=args.upstream,
            port=args.port
        )
    except KeyboardInterrupt:
        print("\nProxy server stopped.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error running proxy server: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lod",
        description="LOD — LLM-Optimized Documentation. API schema governance for LLM pipelines.",
        epilog="Run 'lod <command> --help' for command-specific options."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"lod {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- compile ---
    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile an OpenAPI spec into LLM-optimized format"
    )
    compile_parser.add_argument("-i", "--input", required=True, help="Path to the input OpenAPI JSON file")
    compile_parser.add_argument("-o", "--output", help="Path to the output file (stdout if omitted)")
    compile_parser.add_argument(
        "--model",
        choices=["claude", "gpt", "gemini"],
        help="Target LLM model: 'claude' (XML), 'gpt' (YAML), 'gemini' (TypeScript)"
    )
    compile_parser.set_defaults(func=cmd_compile)

    # --- check ---
    check_parser = subparsers.add_parser(
        "check",
        help="Detect breaking schema drift between two OpenAPI specs"
    )
    check_parser.add_argument("-i", "--input", required=True, help="Path to the current OpenAPI JSON file")
    check_parser.add_argument(
        "-b", "--baseline", required=True,
        help="Baseline spec: file path, URL, or registry:// URI"
    )
    check_parser.set_defaults(func=cmd_check)

    # --- remediate ---
    remediate_parser = subparsers.add_parser(
        "remediate",
        help="Detect breaking drift and auto-create a GitHub PR with the updated LLM spec"
    )
    remediate_parser.add_argument("-i", "--input", required=True, help="Path to the current OpenAPI JSON file")
    remediate_parser.add_argument(
        "-b", "--baseline", required=True,
        help="Baseline spec: file path, URL, or registry:// URI"
    )
    remediate_parser.add_argument("--git-repo", required=True, help="Target GitHub repository (format: owner/repo)")
    remediate_parser.add_argument("--target-file", required=True, help="Path to the LLM prompt spec file to update")
    remediate_parser.add_argument("--git-token", help="GitHub PAT (defaults to GITHUB_TOKEN env var)")
    remediate_parser.add_argument(
        "--model",
        choices=["claude", "gpt", "gemini"],
        help="Target LLM model for the remediated spec"
    )
    remediate_parser.add_argument(
        "--verify-cmd",
        help="Command to verify the remediated prompt locally before pushing to remote repository"
    )
    remediate_parser.add_argument(
        "--allow-failed-verification",
        action="store_true",
        help="Allow remediation PR to be created even if the verification command fails"
    )
    remediate_parser.set_defaults(func=cmd_remediate)

    # --- benchmark ---
    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Generate a token footprint and cost savings report"
    )
    benchmark_parser.add_argument("-i", "--input", required=True, help="Path to the input OpenAPI JSON file")
    benchmark_parser.add_argument(
        "--model",
        choices=["claude", "gpt", "gemini"],
        help="Target LLM model for comparison"
    )
    benchmark_parser.set_defaults(func=cmd_benchmark)

    # --- registry ---
    registry_parser = subparsers.add_parser(
        "registry",
        help="Versioned schema registry commands"
    )
    registry_subparsers = registry_parser.add_subparsers(dest="registry_action")

    reg_register = registry_subparsers.add_parser("register", help="Register a spec version locally")
    reg_register.add_argument("-i", "--input", required=True, help="Path to input spec JSON")
    reg_register.add_argument("--spec-id", required=True, help="Unique identifier for the specification")
    reg_register.add_argument("--tag", required=True, help="Version tag (e.g. v1.0.0)")

    reg_get = registry_subparsers.add_parser("get", help="Retrieve a versioned spec from the registry")
    reg_get.add_argument("--spec-id", required=True, help="Unique identifier for the specification")
    reg_get.add_argument("--tag", required=True, help="Version tag (e.g. v1.0.0)")
    reg_get.add_argument("-o", "--output", required=True, help="Path to save the output JSON spec")

    registry_parser.set_defaults(func=cmd_registry)

    # --- proxy ---
    proxy_parser = subparsers.add_parser(
        "proxy",
        help="Start the dynamic request validation proxy server"
    )
    proxy_parser.add_argument("-i", "--input", required=True, help="Path to the input OpenAPI JSON file")
    proxy_parser.add_argument(
        "-u", "--upstream",
        required=True,
        help="Upstream API target destination (e.g. https://api.example.com)"
    )
    proxy_parser.add_argument(
        "-p", "--port",
        type=int,
        default=8080,
        help="Local listening port (default: 8080)"
    )
    proxy_parser.set_defaults(func=cmd_proxy)

    # Parse and dispatch
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
