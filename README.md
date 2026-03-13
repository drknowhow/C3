# Code Context Control (C3)

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Sponsor](https://img.shields.io/badge/sponsor-drknowhow-ea4aaa.svg?logo=github-sponsors)](https://github.com/sponsors/drknowhow)

C3 is a local code-intelligence layer for AI coding tools. The useful core is narrow: retrieve less, read less, and offload heavy analysis locally when that actually saves context.

## Recommended Default

New installs should use the guided `init` flow with direct MCP mode:

**Windows:**
```bash
install.bat
```

**Mac/Linux:**
```bash
./install.sh
```

Once installed, `c3` is available globally:

```bash
c3 init /path/to/project
```

`c3 init` walks through IDE selection, optional local `git init`, and optional MCP installation.

If you want the same behavior without prompts:

```bash
c3 init /path/to/project --force --git --ide codex --mcp-mode direct
```

`direct` points the IDE straight at `cli/mcp_server.py`.

`proxy` is still available, but it is now an advanced mode for teams that explicitly want dynamic tool filtering experiments:

```bash
c3 install-mcp /path/to/project --mcp-mode proxy
```

`install-mcp` also accepts IDE shorthand positionally when you are already in the project directory:

```bash
c3 install-mcp claude
c3 install-mcp codex
c3 install-mcp . gemini
```

## Lean Workflow

Use these tools by default:

- `c3_recall` when the topic may have prior history
- `c3_search` to locate code
- `c3_file_map` before larger code reads
- `c3_compress` for understanding-only passes
- `c3_extract` before `.log`, `.txt`, or `.jsonl`
- `c3_delegate` for heavy non-editing analysis
- `c3_session_log` and `c3_remember` for durable decisions and conventions

## What Changed

- Direct MCP mode is the recommended install path.
- `c3 init` now provides a step-wise setup menu for IDE, local Git, and MCP.
- Proxy mode is optional and documented as advanced.
- Savings footers, nudges, and response padding are disabled by default.
- Generated instruction files now describe a pragmatic workflow instead of a maximal ritual.
- `c3 init` and `install-mcp` now sync `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` into the project root.
- `install-mcp` now creates project-local `.codex/config.toml` and `.gemini/settings.json` session configs for new projects.
- The context-budget agent now warns before threshold crossings and automatically captures a snapshot at L2 so recovery is faster after `/clear`.

## Tiered Local AI (Hybrid Intelligence)

C3 now features a sophisticated three-tier local intelligence system powered by Ollama:

- **Tier 1 (Nano):** Ultra-fast intent classification and routing using `qwen2:0.5b`. Sub-100ms classification ensures the right tool is used for every task.
- **Tier 2 (Micro):** Efficient Q&A and summarization using models like `deepseek-r1:1.5b`. Ideal for "last-turn" context retrieval and session summaries.
- **Tier 3 (Base):** Complex code analysis and technical reasoning using `llama3.2:3b` or larger.

### Advanced Optimizations
- **Real-time Streaming:** Token-by-token response delivery via SSE for an instant, responsive UI experience.
- **Semantic Caching:** Persistent disk-based cache for LLM results reduces latency for repeated tasks to zero.
- **Dynamic Context Control:** Automatic `num_ctx` optimization right-sizes the model context window for every task type.

## High-Value Tools

- `c3_search`: narrow code retrieval
- `c3_read`: surgical reading of symbols (classes, functions) or line ranges
- `c3_file_map`: structural map for targeted reads
- `c3_compress`: token-reduced file understanding
- `c3_extract`: log/data pre-filtering
- `c3_delegate`: local Ollama offload for heavy analysis

## Benchmarking

```bash
c3 benchmark /path/to/project
```

When local Ollama is available, `c3_delegate` is measured and included in the main benchmark scorecard rather than being treated as an optional side metric.

## Advanced / Optional

These remain available, but they are not part of the recommended default path:

- Proxy-driven dynamic tool filtering
- `c3_route`
- `c3_summarize`
- `c3_raw`
- `c3_why_context`
- `c3_token_stats`
- `c3_context_status`
- `c3_notifications`
- CLAUDE.md lifecycle tools

## Web UI

```bash
c3 ui /path/to/project
```

The UI now treats direct MCP mode as the recommended default and labels proxy mode as advanced.

## Notes

- Claude Code hooks still enforce large-read and log-read guardrails when installed.
- `--git` runs a local-only `git init`; it does not add remotes or use any hosted service.
- Existing installs are not automatically migrated; rerun `install-mcp` or `init --force` to switch defaults.
- Legacy `SHOW_SAVINGS_SUMMARY` config is still honored for compatibility.

## Support C3

C3 is free and open source. If it saves you tokens, extends your sessions, and makes your AI coding workflow better, consider supporting its development. Every contribution helps keep the project maintained and improving.

[![Sponsor on GitHub](https://img.shields.io/badge/sponsor-drknowhow-ea4aaa.svg?logo=github-sponsors&style=for-the-badge)](https://github.com/sponsors/drknowhow)

## License

This project is licensed under the [MIT License](LICENSE).

## Disclaimer

*Created by AI, for AI — via Dr. Know How's hard work.*

---

C3 is provided "as is", without warranty of any kind, express or implied. Token savings, session length improvements, and benchmark figures are based on internal testing — actual results may vary. C3 is not affiliated with, endorsed by, or officially connected to Anthropic, OpenAI, or any AI model provider. The authors are not responsible for any data loss, unexpected behavior, or costs incurred through use of this software. C3 runs entirely locally and does not transmit your code or project data to external servers.
