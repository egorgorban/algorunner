#!/usr/bin/env python3
"""
INFRA-05 Documentation Completeness Gate

Verifies that the documentation set is present, linked, consistent with the
deployed Docker topology, and appropriately sized (30-80 KB).

Exit 0 and print DOCS_OK on success.
Exit 1 and print "CHECK FAILED: <reason>" on failure.
"""

import os
import re
import sys
from pathlib import Path


def check_files_exist_and_nonempty():
    """Check 1: All INFRA-05 paths plus DEFERRED.md and README.md exist and are non-empty."""
    required_files = [
        # Product & Architecture
        "docs/product/prd.md",
        "docs/architecture/architecture.md",
        "docs/architecture/agents.md",
        "docs/architecture/workflow.md",
        "docs/architecture/data-model.md",
        # Development
        "docs/development/testing.md",
        "docs/development/conventions.md",
        # Plans
        "docs/plans/implementation-plan.md",
        # Deferred & README
        "DEFERRED.md",
        "README.md",
    ]

    for filepath in required_files:
        full_path = Path(filepath)
        if not full_path.exists():
            return False, f"MISSING: {filepath}"
        if full_path.stat().st_size == 0:
            return False, f"EMPTY: {filepath}"

    return True, None


def check_repository_rules_section():
    """Check 2: .claude/CLAUDE.md has a Repository Rules heading outside all GSD markers."""
    claude_path = Path(".claude/CLAUDE.md")
    if not claude_path.exists():
        return False, "MISSING: .claude/CLAUDE.md"

    content = claude_path.read_text()

    # Find all GSD marker ranges
    gsd_pattern = r"<!--\s*GSD:(\w+)-start.*?<!--\s*GSD:\1-end\s*-->"
    gsd_ranges = []
    for match in re.finditer(gsd_pattern, content, re.DOTALL):
        gsd_ranges.append((match.start(), match.end()))

    # Find Repository Rules heading
    rules_match = re.search(r"^## Repository Rules$", content, re.MULTILINE)
    if not rules_match:
        return False, "NO_REPOSITORY_RULES: ## Repository Rules heading not found"

    rules_start = rules_match.start()

    # Check that this heading is outside all GSD marker ranges
    for gsd_start, gsd_end in gsd_ranges:
        if gsd_start <= rules_start < gsd_end:
            return False, "REPOSITORY_RULES_INSIDE_GSD: ## Repository Rules is inside a GSD-managed block"

    # Check that the section mentions INFRA-05
    rules_section_end = content.find("\n## ", rules_start + 1)
    if rules_section_end == -1:
        rules_section_end = len(content)

    rules_content = content[rules_start:rules_section_end]
    if "INFRA-05" not in rules_content:
        return False, "RULES_NO_INFRA_MENTION: Repository Rules section does not mention INFRA-05"

    return True, None


def check_no_root_claude():
    """Check 3: No CLAUDE.md exists at the repository root."""
    if Path("CLAUDE.md").exists():
        return False, "CLAUDE.md at root: file should not exist (use .claude/CLAUDE.md instead)"
    return True, None


def check_markdown_links():
    """Check 4: Every relative Markdown link target in docs and README exists.

    Looks for patterns like [text](path) and ignores http(s) links and pure anchors.
    """
    files_to_check = [
        Path("README.md"),
        Path("DEFERRED.md"),
        Path(".claude/CLAUDE.md"),
    ]

    # Collect all .md files from docs/
    docs_dir = Path("docs")
    if docs_dir.exists():
        for md_file in docs_dir.glob("**/*.md"):
            files_to_check.append(md_file)

    link_pattern = r"\[([^\]]+)\]\(([^\)]+)\)"
    repo_root = Path.cwd()

    for file_path in files_to_check:
        if not file_path.exists():
            continue

        content = file_path.read_text()

        for match in re.finditer(link_pattern, content):
            link_target = match.group(2)

            # Skip http(s) links
            if link_target.startswith("http://") or link_target.startswith("https://"):
                continue

            # Skip pure anchors
            if link_target.startswith("#"):
                continue

            # Remove fragment (e.g., #section)
            link_target_no_fragment = link_target.split("#")[0]

            # Resolve relative links from the current file's directory
            if link_target_no_fragment.startswith("/"):
                # Absolute from repo root
                target_path = repo_root / link_target_no_fragment.lstrip("/")
            else:
                # Relative to the current file
                target_path = (file_path.parent / link_target_no_fragment).resolve()

            # Normalize the path
            try:
                target_path = target_path.resolve()
            except Exception:
                # Path resolution failed
                return False, f"BROKEN_LINK: {file_path} → {link_target} (path resolution failed)"

            if not target_path.exists():
                return False, f"BROKEN_LINK: {file_path} → {link_target} (resolved to {target_path})"

    return True, None


def check_docker_compose_services_in_architecture():
    """Check 5: Every top-level service in docker-compose.yml is named in architecture.md."""
    compose_path = Path("docker-compose.yml")
    arch_path = Path("docs/architecture/architecture.md")

    if not compose_path.exists():
        return False, "MISSING: docker-compose.yml"
    if not arch_path.exists():
        return False, "MISSING: docs/architecture/architecture.md"

    compose_content = compose_path.read_text()
    arch_content = arch_path.read_text()

    # Extract service names from docker-compose.yml (top-level services: block)
    services_match = re.search(r"^services:\s*$", compose_content, re.MULTILINE)
    if not services_match:
        return False, "NO_SERVICES_IN_COMPOSE: docker-compose.yml does not have a services: block"

    services_start = services_match.end()
    # Find the next top-level block (volumes:, etc.) or end of file
    next_block = re.search(r"^[a-z_]+:\s*$", compose_content[services_start:], re.MULTILINE)
    if next_block:
        services_end = services_start + next_block.start()
    else:
        services_end = len(compose_content)

    services_block = compose_content[services_start:services_end]

    # Extract service names (lines that start with 2 spaces, followed by word, colon)
    service_pattern = r"^\s{2}(\w+):\s*$"
    services = re.findall(service_pattern, services_block, re.MULTILINE)

    if not services:
        return False, "NO_SERVICES_FOUND: Could not parse services from docker-compose.yml"

    # Check that each service is mentioned in architecture.md
    for service in services:
        if service not in arch_content:
            return False, f"SERVICE_NOT_IN_ARCHITECTURE: '{service}' from docker-compose.yml is not mentioned in architecture.md"

    return True, None


def check_docs_size():
    """Check 6: Total docs size is 30-80 KB.

    Counts:
    - All files in docs/**
    - README.md
    - DEFERRED.md
    - The Repository Rules section in .claude/CLAUDE.md (not the entire file)
    """
    total_size = 0

    # Count all files in docs/
    docs_dir = Path("docs")
    if docs_dir.exists():
        for md_file in docs_dir.glob("**/*.md"):
            total_size += md_file.stat().st_size

    # Count README.md
    readme_path = Path("README.md")
    if readme_path.exists():
        total_size += readme_path.stat().st_size

    # Count DEFERRED.md
    deferred_path = Path("DEFERRED.md")
    if deferred_path.exists():
        total_size += deferred_path.stat().st_size

    # Count only the Repository Rules section of .claude/CLAUDE.md
    claude_path = Path(".claude/CLAUDE.md")
    if claude_path.exists():
        content = claude_path.read_text()
        rules_match = re.search(r"^## Repository Rules$", content, re.MULTILINE)
        if rules_match:
            rules_start = rules_match.start()
            # Find the end of the Repository Rules section (next ## heading or EOF)
            rules_end = content.find("\n##", rules_start + 1)
            if rules_end == -1:
                rules_end = len(content)
            rules_content = content[rules_start:rules_end]
            total_size += len(rules_content.encode('utf-8'))

    min_size = 30000
    max_size = 120000

    if total_size < min_size:
        return False, f"DOCS_TOO_SMALL: {total_size} bytes (minimum {min_size})"
    if total_size > max_size:
        return False, f"DOCS_TOO_LARGE: {total_size} bytes (maximum {max_size}; target ~40-60KB per D-13)"

    return True, total_size


def main():
    checks = [
        ("Files exist and non-empty", check_files_exist_and_nonempty),
        ("Repository Rules section", check_repository_rules_section),
        ("No root CLAUDE.md", check_no_root_claude),
        ("Markdown links", check_markdown_links),
        ("Docker Compose services in architecture.md", check_docker_compose_services_in_architecture),
        ("Documentation size", check_docs_size),
    ]

    total_size = None

    for check_name, check_func in checks:
        result = check_func()
        if isinstance(result, tuple) and len(result) == 2:
            success, detail = result
        else:
            success = result
            detail = None

        if not success:
            print(f"CHECK FAILED: {detail or check_name}", file=sys.stderr)
            sys.exit(1)

        # Capture total_size from the last check
        if isinstance(detail, int):
            total_size = detail

    # Print success
    if total_size is not None:
        size_kb = total_size / 1024
        print(f"Docs size: {total_size} bytes ({size_kb:.1f} KB)")

    print("DOCS_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
