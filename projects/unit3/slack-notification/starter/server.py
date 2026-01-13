#!/usr/bin/env python3
"""
Module 3: Slack Notification Integration
Combines all MCP primitives (Tools and Prompts) for complete team communication workflows.
"""

import json
import os
import sys
from typing import Optional
from pathlib import Path
from datetime import datetime

import anyio
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("pr-agent")

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
EVENTS_FILE = Path(__file__).parent / "github_events.json"

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

def get_cwd(working_directory: Optional[str]) -> str:
    """Get the current working directory."""
    try:
        if working_directory:
            return str(Path(working_directory).resolve())
        return str(Path.cwd().resolve())
    except Exception as e:
        raise ValueError(f"Error resolving working directory: {str(e)}")
            
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
        cwd = get_cwd(working_directory)
        
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


@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    # Read events from file
    if not EVENTS_FILE.exists():
        return json.dumps([])
    
    with open(EVENTS_FILE, 'r') as f:
        events = json.load(f)
    
    # Return most recent events
    recent = events[-limit:]
    return json.dumps(recent, indent=2)


@mcp.tool()
async def get_workflow_status(workflow_name: Optional[str] = None) -> str:
    """Get the current status of GitHub Actions workflows.
    
    Args:
        workflow_name: Optional specific workflow name to filter by
    """
    # Read events from file
    if not EVENTS_FILE.exists():
        return json.dumps({"message": "No GitHub Actions events received yet"})
    
    with open(EVENTS_FILE, 'r') as f:
        events = json.load(f)
    
    if not events:
        return json.dumps({"message": "No GitHub Actions events received yet"})
    
    # Filter for workflow events
    workflow_events = [
        e for e in events 
        if e.get("workflow_run") is not None
    ]
    
    if workflow_name:
        workflow_events = [
            e for e in workflow_events
            if e["workflow_run"].get("name") == workflow_name
        ]
    
    # Group by workflow and get latest status
    workflows = {}
    for event in workflow_events:
        run = event["workflow_run"]
        name = run["name"]
        if name not in workflows or run["updated_at"] > workflows[name]["updated_at"]:
            workflows[name] = {
                "name": name,
                "status": run["status"],
                "conclusion": run.get("conclusion"),
                "run_number": run["run_number"],
                "updated_at": run["updated_at"],
                "html_url": run["html_url"]
            }
    
    return json.dumps(list(workflows.values()), indent=2)


# ===== New Module 3: Slack Integration Tools =====

@mcp.tool()
async def send_slack_notification(message: str) -> str:
    """Send a formatted notification to the team Slack channel.
    
    Args:
        message: The message to send to Slack (supports Slack markdown)
    """
    from dotenv import load_dotenv
    load_dotenv()
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        return "Error: SLACK_WEBHOOK_URL environment variable not set"
    
    try:
        # TODO: Import requests library
        # TODO: Send POST request to webhook_url with JSON payload
        # TODO: Include the message in the JSON data
        # TODO: Handle the response and return appropriate status
        import requests
        payload = {
            "text": message
        }

        request = requests.post(webhook_url, json=payload)
        if request.status_code == 200:
            return "Slack Notification sent successfully"
        return f"Error ({request.status_code}) sending Slack notification: {request.text}"
        
    except Exception as e:
        return f"Error sending message: {str(e)}"


# ===== New Module 3: Slack Formatting Prompts =====

@mcp.prompt()
async def format_ci_failure_alert():
    """Create a Slack alert for CI/CD failures with rich formatting."""
    return """Format this GitHub Actions failure as a Slack message using ONLY Slack markdown syntax:

❌ *CI Failed* - [Repository Name]

> Brief summary of what failed

*Details:*
• Workflow: `workflow_name`
• Branch: `branch_name`  
• Commit: `commit_hash`

*Next Steps:*
• <https://github.com/test/repo/actions/runs/123|View Action Logs>

CRITICAL: Use EXACT Slack link format: <https://full-url|Link Text>
Examples:
- CORRECT: <https://github.com/user/repo|Repository>
- WRONG: [Repository](https://github.com/user/repo)
- WRONG: https://github.com/user/repo

Other Slack formats:
- *text* for bold (NOT **text**)
- `text` for code
- > text for quotes
- • for bullets"""


@mcp.prompt()
async def format_ci_success_summary():
    """Create a Slack message celebrating successful deployments."""
    return """Format this successful GitHub Actions run as a Slack message using ONLY Slack markdown syntax:

✅ *Deployment Successful* - [Repository Name]

> Brief summary of what was deployed

*Changes:*
• Key feature or fix 1
• Key feature or fix 2

*Links:*
• <https://github.com/user/repo|View Changes>

CRITICAL: Use EXACT Slack link format: <https://full-url|Link Text>
Examples:
- CORRECT: <https://github.com/user/repo|Repository>
- WRONG: [Repository](https://github.com/user/repo)
- WRONG: https://github.com/user/repo

Other Slack formats:
- *text* for bold (NOT **text**)
- `text` for code
- > text for quotes
- • for bullets"""


# ===== Prompts from Module 2 (Complete) =====

@mcp.prompt()
async def analyze_ci_results():
    """Analyze recent CI/CD results and provide insights."""
    return """Please analyze the recent CI/CD results from GitHub Actions:

1. First, call get_recent_actions_events() to fetch the latest CI/CD events
2. Then call get_workflow_status() to check current workflow states
3. Identify any failures or issues that need attention
4. Provide actionable next steps based on the results

Format your response as:
## CI/CD Status Summary
- **Overall Health**: [Good/Warning/Critical]
- **Failed Workflows**: [List any failures with links]
- **Successful Workflows**: [List recent successes]
- **Recommendations**: [Specific actions to take]
- **Trends**: [Any patterns you notice]"""


@mcp.prompt()
async def create_deployment_summary():
    """Generate a deployment summary for team communication."""
    return """Create a deployment summary for team communication:

1. Check workflow status with get_workflow_status()
2. Look specifically for deployment-related workflows
3. Note the deployment outcome, timing, and any issues

Format as a concise message suitable for Slack:

🚀 **Deployment Update**
- **Status**: [✅ Success / ❌ Failed / ⏳ In Progress]
- **Environment**: [Production/Staging/Dev]
- **Version/Commit**: [If available from workflow data]
- **Duration**: [If available]
- **Key Changes**: [Brief summary if available]
- **Issues**: [Any problems encountered]
- **Next Steps**: [Required actions if failed]

Keep it brief but informative for team awareness."""


@mcp.prompt()
async def generate_pr_status_report():
    """Generate a comprehensive PR status report including CI/CD results."""
    return """Generate a comprehensive PR status report:

1. Use analyze_file_changes() to understand what changed
2. Use get_workflow_status() to check CI/CD status
3. Use suggest_template() to recommend the appropriate PR template
4. Combine all information into a cohesive report

Create a detailed report with:

## 📋 PR Status Report

### 📝 Code Changes
- **Files Modified**: [Count by type - .py, .js, etc.]
- **Change Type**: [Feature/Bug/Refactor/etc.]
- **Impact Assessment**: [High/Medium/Low with reasoning]
- **Key Changes**: [Bullet points of main modifications]

### 🔄 CI/CD Status
- **All Checks**: [✅ Passing / ❌ Failing / ⏳ Running]
- **Test Results**: [Pass rate, failed tests if any]
- **Build Status**: [Success/Failed with details]
- **Code Quality**: [Linting, coverage if available]

### 📌 Recommendations
- **PR Template**: [Suggested template and why]
- **Next Steps**: [What needs to happen before merge]
- **Reviewers**: [Suggested reviewers based on files changed]

### ⚠️ Risks & Considerations
- [Any deployment risks]
- [Breaking changes]
- [Dependencies affected]"""


@mcp.prompt()
async def troubleshoot_workflow_failure():
    """Help troubleshoot a failing GitHub Actions workflow."""
    return """Help troubleshoot failing GitHub Actions workflows:

1. Use get_recent_actions_events() to find recent failures
2. Use get_workflow_status() to see which workflows are failing
3. Analyze the failure patterns and timing
4. Provide systematic troubleshooting steps

Structure your response as:

## 🔧 Workflow Troubleshooting Guide

### ❌ Failed Workflow Details
- **Workflow Name**: [Name of failing workflow]
- **Failure Type**: [Test/Build/Deploy/Lint]
- **First Failed**: [When did it start failing]
- **Failure Rate**: [Intermittent or consistent]

### 🔍 Diagnostic Information
- **Error Patterns**: [Common error messages or symptoms]
- **Recent Changes**: [What changed before failures started]
- **Dependencies**: [External services or resources involved]

### 💡 Possible Causes (ordered by likelihood)
1. **[Most Likely]**: [Description and why]
2. **[Likely]**: [Description and why]
3. **[Possible]**: [Description and why]

### ✅ Suggested Fixes
**Immediate Actions:**
- [ ] [Quick fix to try first]
- [ ] [Second quick fix]

**Investigation Steps:**
- [ ] [How to gather more info]
- [ ] [Logs or data to check]

**Long-term Solutions:**
- [ ] [Preventive measure]
- [ ] [Process improvement]

### 📚 Resources
- [Relevant documentation links]
- [Similar issues or solutions]"""


if __name__ == "__main__":
    # Run MCP server normally
    print("Starting PR Agent Slack MCP server...")
    print("Make sure to set SLACK_WEBHOOK_URL environment variable")
    print("To receive GitHub webhooks, run the webhook server separately:")
    print("  python webhook_server.py")
    mcp.run()