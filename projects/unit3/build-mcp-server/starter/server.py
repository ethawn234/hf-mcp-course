#!/usr/bin/env python3
"""
Module 1: Basic MCP Server with PR Template Tools
A minimal MCP server that provides tools for analyzing file changes and suggesting PR templates.
"""
import json
import os
import sys
from typing import Optional
from pathlib import Path

import anyio
from mcp.server.fastmcp import FastMCP, Context

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# PR template directory
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

async def run_git_command(args: list[str], cwd: str) -> tuple[str, str, int]:
    """Run a git command asynchronously using a thread pool."""
    import subprocess
    
    def _run():
        env = os.environ.copy()
        
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=30)
            return stdout, stderr, proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return "", "Command timed out", 1
    
    try:
        return await anyio.to_thread.run_sync(_run, abandon_on_cancel=True)
    except Exception as e:
        return "", str(e), 1


@mcp.tool()
async def analyze_file_changes(
    ctx: Context,
    working_directory: str,
    base_branch: str = "main",
    target_branch: Optional[str] = None,
    include_diff: bool = True,
    max_diff_lines: int = 500    
) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        working_directory: The git repository directory to analyze (required - pass the user's workspace folder)
        base_branch: Base branch to compare against (default: main)
        target_branch: Branch to compare (default: HEAD/current branch). Can be a branch name like 'feature/my-feature'
        include_diff: Include the full diff content (default: true)
        max_diff_lines: Maximum number of diff lines to include (default: 500)
    """
    try:
        cwd = str(Path(working_directory).resolve())
        
        if not os.path.isdir(cwd):
            return json.dumps({"error": f"Directory does not exist: {cwd}"})
        
        target = target_branch if target_branch else "HEAD"
        
        # get current branch name if target_branch is not provided
        await ctx.info("Running git branch --show-current")
        target_branch_stdout, target_branch_stderr, target_branch_rc = await run_git_command(
            ["git", "branch", "--show-current"], cwd
        )
        await ctx.info(f"git branch --show-current done, {target_branch_stdout.strip()}")
        # if first git cmd fails, subsequent cmds likely will too
        if target_branch_rc != 0:
            return json.dumps({"error": f"Git error: {target_branch_stderr}", "_debug": debug_info})
            
        await ctx.info(f"Starting analyze_file_changes, cwd={cwd}")
        await ctx.info(f"Comparing {base_branch}...{target}")
        
        debug_info = {
            "provided_working_directory": working_directory,
            "actual_cwd": cwd,
            "server_process_cwd": os.getcwd(),
            "server_file_location": str(Path(__file__).parent),
            "base_branch": base_branch,
            "target_branch": target_branch_stdout.strip() if not target_branch else target_branch,
            "roots_check": None
        }
        
        await ctx.info("Running git diff --name-status")
        
        # Get list of changed files
        changed_files_stdout, _, _ = await run_git_command(
            ["git", "diff", "--name-status", f"{base_branch}...{target}"],
            cwd
        )
        
        await ctx.info("Running git diff --stat")
        
        # Get diff statistics
        stat_stdout, _, _ = await run_git_command(
            ["git", "diff", "--stat", f"{base_branch}...{target}"],
            cwd
        )
        await ctx.info("git diff --stat done")
        
        # Get the actual diff if requested
        diff_content = ""
        truncated = False
        diff_lines = []
        if include_diff:
            await ctx.info("Running git diff")
            diff_stdout, _, _ = await run_git_command(
                ["git", "diff", f"{base_branch}...{target}"],
                cwd
            )
            await ctx.info("git diff done")
            diff_lines = diff_stdout.split('\n')
            
            if len(diff_lines) > max_diff_lines:
                diff_content = '\n'.join(diff_lines[:max_diff_lines])
                diff_content += f"\n\n... Output truncated. Showing {max_diff_lines} of {len(diff_lines)} lines ..."
                diff_content += "\n... Use max_diff_lines parameter to see more ..."
                truncated = True
            else:
                diff_content = diff_stdout
        
        # Get commit messages for context
        commits_stdout, _, _ = await run_git_command(
            ["git", "log", "--oneline", f"{base_branch}..{target}"],
            cwd
        )
        
        analysis = {
            "base_branch": base_branch,
            "target_branch": target_branch_stdout.strip() if not target_branch else target_branch,
            "files_changed": changed_files_stdout,
            "statistics": stat_stdout,
            "commits": commits_stdout,
            "truncated": truncated,
            "total_diff_lines": len(diff_lines),
            "_debug": debug_info,
            "diff": diff_content if include_diff else "Diff not included (set include_diff=true to see full diff)"
        }

        return json.dumps(analysis, indent=2)
        
    except TimeoutError:
        return json.dumps({"error": "Git command timed out"})
    except Exception as e:
        return json.dumps({"error": str(e)})

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
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)
    
    template_file = TYPE_MAPPING.get(change_type.lower(), "feature.md")
    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0]  # Default to first template if no match
    )
    
    suggestion = {
        "recommended_template": selected_template,
        "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
        "template_content": selected_template["content"],
        "usage_hint": "Claude can help you fill out this template based on the specific changes in your PR."
    }
    
    return json.dumps(suggestion, indent=2)

if __name__ == "__main__":
    mcp.run()