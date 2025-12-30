#!/usr/bin/env python3
import sys
import asyncio
import os
from typing import Optional

"""
Module 1: Basic MCP Server - Starter Code
TODO: Implement tools for analyzing git changes and suggesting PR templates
"""

import json
import subprocess
from pathlib import Path
from urllib.request import url2pathname

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# PR template directory (shared across all modules)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Default PR templates
DEFAULT_TEMPLATES = {
    "bug.md": "Bug Fix",
    "feature.md": "Feature",
    "docs.md": "Documentation",
    "refactor.md": "Refactor",
    "test.md": "Test",
    "performance.md": "Performance",
    "security.md": "Security"
}

# Type mapping for PR templates
TYPE_MAPPING = {
    "bug": "bug.md",
    "fix": "bug.md",
    "feature": "feature.md",
    "enhancement": "feature.md",
    "docs": "docs.md",
    "documentation": "docs.md",
    "refactor": "refactor.md",
    "cleanup": "refactor.md",
    "test": "test.md",
    "testing": "test.md",
    "performance": "performance.md",
    "optimization": "performance.md",
    "security": "security.md"
}

@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main", 
    include_diff: bool = True, 
    max_diff_lines: int = 500,
    working_directory: Optional[str] = None
    ) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        - base_branch: Base branch to compare against (default: main)
        - include_diff: Include the full diff content (default: true)
    """    
    
    try:
        # get working directory 
        # By default, MCP servers run commands in their installation directory, not in agent's current working directory. This means your git commands might analyze the wrong repository!
        uri_path = None
        if working_directory is None:
            try:
                context = mcp.get_context()
                roots_result = await context.session.list_roots()
                #get first root (this will be the cwd)
                root = roots_result.roots[0]
                uri_path = root.uri.path
                # Convert file:// URI to native path (handles /C:/... on Windows)
                working_directory = url2pathname(uri_path)
            except Exception:
                # if no root, fall back to current dir
                pass

        cwd = str(Path(working_directory if working_directory else os.getcwd()).resolve())

        # get summary statistics
        stats_output = subprocess.run(
            ["git", "diff", "--stat", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd
        )

        # get names of changed files
        changed_filenames = subprocess.run(
            ["git", "diff", "--name-status", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd
        )

        # if include_diff=True, get from last common commit
        if include_diff:
            diff = subprocess.run(
                ["git", "diff", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=cwd
                )

            diff_output = diff.stdout
            diff_lines = diff_output.split('\n')

            # truncate diff if needed
            if len(diff_lines) > max_diff_lines:
                truncated_diff = '\n'.join(diff_lines[:max_diff_lines])
                truncated_diff += f"\n\n... Diff truncated. Showing {max_diff_lines} of {len(diff_lines)}"
                diff_output = truncated_diff
            
        return json.dumps({
            "cwd": cwd,
            "statistics": stats_output.stdout,
            "total_lines": len(diff_output),
            "files_changed": changed_filenames.stdout,
            "diff_output": diff_output if include_diff else "set include_diff=true to see full diff"
        }, indent=2)

    except Exception as e:
        return json.dumps({ "error": str(e), "uri_path": uri_path, "cwd": cwd })

@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    templates = [
        {
            "filename": filename,
            "type": template_type,
            "content": (TEMPLATES_DIR / filename).read_text()
        }
        for filename, template_type in DEFAULT_TEMPLATES.items()
    ]
    
    return json.dumps(templates, indent=2)


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    # get templates
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)

    # find matching template
    template_file = TYPE_MAPPING.get(change_type.lower(), "feature.md")
    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0]
    )

    suggestion = {
        "recommended_template": selected_template,
        "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
        "template_content": selected_template["content"],
        "usage_hint": "Claude can help you fill out this template based on the specific changes in your PR."
    }
    
    return json.dumps(suggestion, indent=2)


if __name__ == "__main__":
    # add option to run single function
    if len(sys.argv) > 1:
        func_name = sys.argv[1]
        func = globals().get(func_name)
        if func and callable(func):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = asyncio.run(func())
                else:
                    result = func()
                print(f"Running {func_name}: {result}")
            except Exception as e:
                print(f"Error running {func_name}: {e}")
        else:
            print(f"Function '{func_name}' not found or callable.")
    else:
        mcp.run()