# Lessons Learned from [Hugging Face MCP](https://huggingface.co/learn/mcp-course/unit3/introduction)

## Current
- To correct the response object format, add 2nd arg `indent=2` to `json.dumps({}, indent=2)`:

  ```powershell
  {
    "statistics": " .../build-mcp-server/starter/requirements.txt      | Bin 0 -> 1754 bytes\n projects/unit3/build-mcp-server/starter/server.py  |  12 +-\n projects/unit3/build-mcp-server/starter/uv.lock    | 962 +++++++++++++++++++++\n 3 files changed, 973 insertions(+), 1 deletion(-)\n",
    "total_lines": 188,
    "files_changed": "A\tprojects/unit3/build-mcp-server/starter/requirements.txt\nM\tprojects/unit3/build-mcp-server/starter/server.py\nA\tprojects/unit3/build-mcp-server/starter/uv.lock\n",
    "diff_output": "diff --git a/projects/unit3/build-mcp-server/starter/requirements.txt b/projects/unit3/build-mcp-server/starter/requirements.txt\nnew file mode 100644\n\n... Diff truncated. Showing 2 of 1003"
  }
  ```

### Testing my code changes
Validate that my changes work as expected by calling individual functions.

- added logic to `if __name__ == "__main__"` to allow individual functions to be called: 

  `py server.py <function_name>`

### About `git diff`

- `git diff` without additional args returns a diff that omits changes to the lock file. For example, this command will not output the changes in `uv.lock` to the console.

- Running terminal commands in `subprocess.run` seems to require tighter adherence to specs. Manually writing `git diff main HEAD` in the terminal returns the diff output to the console, but not as a subprocess.

### Truncating long diffs
- Subscript the diff output to the length of desire max lines.
- Only invoke if `include_diff=True`.

### Get summary statistics
- cmd: `git diff --stat <base> <topic>`

### Get names of changed files
- cmd: `git diff --name-status <base> <topic>`

### Return function output
- MCP tools should always returned a stringified json. This means the outputs from `subprocess.run` invocations must be processed to extract the desired values.
- The return value of `subprocess.run` is a `CompletedProcess` object. Extract the desired fields and their values.

### Commands

#### Run validations/tests:
- `uv run [py|pytest] <file_name>`

#### Run a single validation/test:
- `uv run [py|pytest] <file_name> <test_name>`

#### Run a single function from a file:
- `uv run <file_name> <function_name>`