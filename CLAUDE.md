## C3 Tooling Mandate (CRITICAL)
Use `c3_*` tools by default. Native IDE search/read tools are fallback-only.


## Required Workflow
- **START**: Call `c3_memory(action='recall', query='...')` or `c3_memory(action='query', query='...')` before exploring code for tasks that may have prior context.
- **DISCOVER**: Call `c3_search(query='...', action='files|code|semantic')` before broad repo search, file listing, or ad-hoc discovery. Use `action='semantic'` for natural-language queries when TF-IDF keyword search is insufficient.
- **MAP**: Call `c3_compress(file_path='...', mode='map|dense_map')` before reading unfamiliar or large files.
- **READ**: Call `c3_read(file_path='...', symbols=['...']|lines=[[start,end]])` before broad file reads. Use native file reads only for a narrow follow-up after C3 narrowing.
- **DATA**: Call `c3_filter(text='...')` for terminal output over 10 lines and `c3_filter(file_path='...')` before reading log, txt, or jsonl files directly.
- **CHECK**: Prefer `c3_validate(file_path='...')` for time-bounded native syntax validation after edits or before reporting completion.
- **LOG**: Use `c3_session(action='log', event_type='decision', ...)` for important decisions. Use `c3_session(action='snapshot')` before `/clear`.


## Automated Budget Management
- **Budget Monitoring**: Check the token budget (via `c3_status(view='budget')`) at the start of each task.
- **Truncation Detection**: If a tool output contains `[ctx:truncated ... | snapshot→new conversation→restore to reset budget]`, it means the tool response was cut short due to high token usage.
- **Proactive Restart**: If the budget is high (>=80%) or critical (>=90%), or if a **Truncation Detection** occurs, proactively prompt the user after finishing the current turn: "Token budget is [XX]% (and/or truncation occurred). Would you like me to automate a session restart? I will take a snapshot and provide you with a one-click restore command for your new conversation."
- **One-Click Restart**: Upon confirmation:
  1. Call `c3_session(action='snapshot', data='automated_restart', summary='Taking snapshot before session restart')`.
  2. Inform the user: "Snapshot taken. Please run `/clear` and then paste: `c3_session(action='restore', data='latest')` to continue immediately."
- **Self-Preservation**: Prioritize this restart over continuing with a bloated context to avoid tool failures or degradation in AI performance.


## Fallback Rules
- Do not start with native repo search, broad file reads, or raw log reads when a matching `c3_*` tool exists.
- Fallback is allowed only if the C3 tool failed, returned insufficient scope, or a tiny follow-up read is faster than another tool round-trip.
- When falling back, state which C3 tool was attempted or skipped and why.


## Reporting Rules
- Mention the `c3_*` tools used when summarizing work.
- If no C3 tool was used for exploration, say why that exception was necessary.


## Core C3 Tools
- `c3_memory(action='recall'|'query')` for cross-session context and memory retrieval.
- `c3_memory(action='export')` for markdown-formatted facts to paste into MEMORY.md topic files.
- `c3_search(action='files'|'code'|'transcript'|'semantic')` for discovery before native search.
- `c3_compress(mode='map'|'dense_map'|'smart')` for structural overview and token-efficient understanding.
- `c3_read(...)` for surgical symbol or line extraction.
- `c3_filter(...)` for noisy terminal, log, txt, and jsonl input.
- `c3_validate(...)` for deterministic, time-bounded syntax validation when available.
- `c3_session(action='log|plan|snapshot|restore|convo_log')` for decisions and continuity.


## Project Context

```
claude-companion - v2/
  .mcp.json
  2
  AGENTS.md
  CLAUDE.md
  GEMINI.md
  README.md
  `${name}
  benchmark-report.html
  c3.bat
  install.bat
  install.sh
  landing.html
  recommended
  requirements.txt
  .claude/
    settings.local.json
  .codex/
    config.toml
  .gemini/
    settings.json
  .github/
    copilot-instructions.md
  .pytest_cache/
    .gitignore
    CACHEDIR.TAG
    v/
      cache/
        lastfailed
        nodeids
  .vscode/
    mcp.json
  cli/
    __init__.py
    _hook_utils.py
    c3.py
    docs.html
    hook_c3read.py
    hook_filter.py
    hook_read.py
    hub.html
    hub_server.py
    mcp_proxy.py
    mcp_server.py
    server.py
    ui.html
    ui_legacy.html
    ui_nano.html
    commands/
      common.py
      parser.py
    tools/
      _helpers.py
      compress.py
      delegate.py
      filter.py
      memory.py
      read.py
      search.py
      session.py
      status.py
      validate.py
    ui/
      api.js
      app.js
      icons.js
      shared.js
      theme.js
      components/
        dashboard.js
        instructions.js
        memory.js
        sessions.js
        settings.js
        sidebar.js
  core/
    config.py
    ide.py
  docs/
    budget-system.md
    token-efficiency-roadmap.md
    superpowers/
      plans/
        .Rhistory
        2026-03-11-simplify-budget-system.md
        2026-03-12-e2e-benchmark-c3-adoption.md
        2026-03-12-licensing-system.md
        access_track.txt
      specs/
        2026-03-12-lean-e2e-benchmark.md
        2026-03-12-monetization-open-core.md
  services/
    activity_log.py
    agent_base.py
    agents.py
    auto_memory.py
    claude_md.py
    compressor.py
    context_snapshot.py
    conversation_store.py
    doc_index.py
    e2e_benchmark.py
    e2e_evaluator.py
    e2e_tasks.py
    embedding_index.py
    file_memory.py
    ... +25 more
  tests/
    test_e2e_benchmark.py
    test_memory_system.py
    test_output_filter.py
    test_project_manager.py
    test_session_benchmark.py
    test_session_budget.py
    test_validate.py
  tui/
    backend.py
    build.bat
    build.sh
    main.py
    theme.tcss
    screens/
      benchmark_view.py
      claudemd_view.py
      compress_view.py
      index_view.py
      init_view.py
      mcp_view.py
      optimize_view.py
      pipe_view.py
      projects_view.py
      search_view.py
      session_view.py
      stats.py
      ui_view.py
    widgets/


## Tech Stack

Python


## Key Files

- `cli/mcp_server.py` — MCP server entry


## Key Facts (use c3_memory for more)

- MCP server and Flask REST server have separate service instances — they share data only through the .c3/ directory on di
- ui.html uses key={tab} on the main content div, which forces full remount of tab components on every tab switch. Any sta
- Global getToolColor() and toolColors map live at the top of ui.html as shared constants. Tool color mapping: search=blue
- [architecture] File Memory system: FileMemoryStore in services/file_memory.py provides persistent structural index of so
- [convention] cmd_install_mcp in c3.py now generates both .mcp.json AND .claude/settings.local.json with PostToolUse hook