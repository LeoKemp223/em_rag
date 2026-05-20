# Interactive Bootstrap for New Projects

## Goal

Make a brand-new project usable with one command, while keeping the first run explicit and readable in Chinese.

The bootstrap flow should:

- Prepare the Python environment
- Initialize the project config
- Generate `.mcp.json`
- Run a health check
- Stop before any document indexing unless the user explicitly asks for it

## User Experience

The repository root will provide two entry scripts:

- `setup.sh`
- `setup.bat`

They are thin launchers only. The actual logic lives in a shared Python bootstrap module so both platforms follow the same behavior.

On first run, the script presents a Chinese interactive flow. It should ask for confirmation before creating or overwriting files and before installing dependencies. The default path is:

1. Detect Python 3.11+
2. Create or reuse a virtual environment
3. Install project dependencies
4. Initialize `.em_rag/config.yaml`
5. Generate `.mcp.json`
6. Run `doctor`

Document indexing is not part of the default bootstrap path.

## Script Responsibilities

`setup.sh` and `setup.bat` only need to:

- Resolve the repository root
- Locate a usable Python interpreter
- Invoke the shared Python bootstrap entrypoint
- Forward any explicit options

The shared bootstrap module owns:

- Chinese prompts
- Environment checks
- File creation and overwrite decisions
- Calling existing CLI commands such as `init`, `mcp`, and `doctor`

## Flow

```text
user runs setup.sh / setup.bat
  -> find Python
  -> ensure venv
  -> install deps
  -> ask whether to initialize project config
  -> write .em_rag/config.yaml
  -> ask whether to generate .mcp.json
  -> write .mcp.json
  -> run doctor
  -> show next manual step for indexing
```

## Behavior Details

- If `.em_rag/config.yaml` already exists, the script should ask before overwriting it.
- If `.mcp.json` already exists, the script should ask before overwriting it.
- If dependency installation fails, the bootstrap stops and reports the failing step.
- If `doctor` reports a missing model or missing SQLite feature, the script should surface that clearly but still finish the bootstrap.
- The script should not auto-index `./docs`, `./examples`, or any other content by default.

## Chinese Prompts

All user-facing prompts in the bootstrap flow should be Chinese and concise.

Examples of prompt categories:

- whether to create a virtual environment
- whether to install dependencies
- whether to initialize the project config
- whether to generate `.mcp.json`
- whether to run an optional model download step

The prompt text should avoid jargon where a plain phrase is enough.

## Error Handling

The bootstrap should fail fast on environment setup problems, but avoid unnecessary hard exits for optional steps.

Expected failure cases:

- Python not found
- Python version below 3.11
- `pip install` failure
- write permission failure for project files
- malformed existing config that cannot be safely preserved

Each failure should identify the step that failed and the file or command involved.

## Acceptance Criteria

The work is complete when:

- A user can run one command from a fresh clone and reach a usable project setup
- The first-run flow is in Chinese
- `setup.sh` and `setup.bat` behave consistently
- No documents are indexed unless explicitly chosen
- Existing `init`, `mcp`, and `doctor` logic is reused instead of duplicated

## Testing

Add tests for:

- bootstrap decision flow
- overwrite prompts
- config and MCP generation
- default no-index behavior
- platform-independent orchestration logic

