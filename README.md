# Code Context Control (C3)

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Sponsor](https://img.shields.io/badge/sponsor-drknowhow-ea4aaa.svg?logo=github-sponsors)](https://github.com/sponsors/drknowhow)

C3 is a local MCP server that gives AI coding tools surgical code understanding instead of brute-force file reads. It runs 100% locally, requires no API keys, and works with any AI tool that supports [Model Context Protocol](https://modelcontextprotocol.io/).

**90% fewer tokens. 4x longer sessions. Measurably better answers.**

---

## Quick Start

### Requirements

- Python 3.10+
- One or more supported AI coding tools (see [Compatibility](#compatibility))
- Optional: [Ollama](https://ollama.com/) for local AI features (semantic search, delegation)

### Install

**Windows:**
```bash
install.bat
```

**Mac/Linux:**
```bash
./install.sh
```

Or manually:
```bash
git clone https://github.com/drknowhow/C3.git
cd C3
pip install -r requirements.txt
```

### Initialize a Project

```bash
c3 init /path/to/project
```

`c3 init` walks through IDE selection, optional local `git init`, and MCP server registration. For non-interactive setup:

```bash
c3 init /path/to/project --force --git --ide claude --mcp-mode direct
```

### Start Coding

Open your AI tool and start working. C3 tools appear automatically via the MCP protocol — no manual configuration needed.

---

## How It Works

Without C3, your AI reads entire files to understand your code. A 340-line file costs ~4,200 tokens even if the AI only needs one function.

With C3, the AI uses targeted tools:

1. **Search** — find relevant files by meaning, not just text (`c3_search`)
2. **Map** — get a structural overview of a file for the cost of a few tokens (`c3_compress`)
3. **Extract** — pull exactly the symbols or line ranges needed (`c3_read`)

The result: the same information delivered in 1/10th the context. Your sessions last longer, your AI gives better answers, and you spend less on tokens.

---

## Tools

### Core Tools

| Tool | Purpose | Example |
|------|---------|---------|
| **c3_search** | Find files by keyword or semantic meaning | `c3_search(query="auth middleware", action="semantic")` |
| **c3_compress** | Structural map of a file — classes, functions, signatures | `c3_compress("services/auth.py", mode="map")` |
| **c3_read** | Extract specific symbols or line ranges from a file | `c3_read("services/auth.py", symbols=["verify_token"])` |
| **c3_validate** | Native syntax checking for 15+ languages with caching | `c3_validate("services/auth.py")` |
| **c3_memory** | Persistent facts, decisions, and conventions across sessions | `c3_memory(action="recall", query="auth pattern")` |
| **c3_filter** | Pre-process logs, terminal output, and data files | `c3_filter(file_path="app.log")` |

### Additional Tools

| Tool | Purpose |
|------|---------|
| **c3_session** | Session logging, snapshots, and restore for continuity across `/clear` |
| **c3_delegate** | Offload heavy analysis to local Ollama models (requires Ollama) |
| **c3_status** | View index health, token budget, and project stats |

### Lean Workflow

Use these tools by default in your AI coding sessions:

- `c3_memory(action="recall")` — when the topic may have prior history
- `c3_search` — to locate code before reading
- `c3_compress` — before reading unfamiliar or large files
- `c3_read` — for surgical symbol or line extraction
- `c3_filter` — before reading `.log`, `.txt`, or `.jsonl` files
- `c3_validate` — after edits, for instant syntax checking

---

## Benchmarking

### Overview

C3 ships with a built-in end-to-end benchmark that measures real-world quality improvements:

```bash
c3 benchmark /path/to/project
```

The benchmark runs 14 tasks across 7 categories on an identical git worktree sandbox — once with C3 MCP tools, once without. Responses are scored across five deterministic dimensions using ground-truth evaluation.

### Key Results

| Metric | Value |
|--------|-------|
| **Token Savings** | 90% (raw tool-level) |
| **Context Multiplier** | 9.87x — same information in 1/10th the tokens |
| **Session Extension** | 4.15x longer before hitting context limits |
| **E2E Win Rate** | 57% (8/14 tasks), 69% weighted by score magnitude |
| **Quality Uplift** | +28% average across all dimensions |
| **Session-Net Savings** | 76% after C3 overhead (mandates, schemas, recalls) |

### Category Breakdown

| Category | Tasks | Difficulty | C3 Score | Baseline | Delta | Result |
|----------|-------|------------|----------|----------|-------|--------|
| Code Review | 2 | Hard | 0.706 | 0.204 | **+50.3pp** | C3 2/2 |
| Bug Detection | 2 | Medium | 0.903 | 0.547 | **+35.5pp** | C3 1/2 |
| Refactoring | 2 | Expert | 0.312 | 0.000 | **+31.2pp** | C3 2/2 |
| Call Chain | 2 | Hard | 0.900 | 0.887 | +1.2pp | C3 1/2 |
| Architecture | 2 | Hard | 0.638 | 0.627 | +1.2pp | C3 1/2 |
| Explanation | 2 | Easy | 0.907 | 0.920 | -1.3pp | Baseline |
| File Discovery | 2 | Easy | 0.783 | 0.839 | -5.6pp | Baseline |

**Model:** Claude Sonnet 4.6 | **Avg Score:** C3 0.736 vs Baseline 0.575 | **C3 21% faster** on average

### Quality Dimensions

Five independent dimensions, each scored 0–100%:

| Dimension | C3 | Baseline | Delta |
|-----------|-----|----------|-------|
| Factual Accuracy | 82.1% | 57.1% | **+25pp** |
| Completeness | 75.0% | 54.8% | **+20pp** |
| File Mentions | 77.4% | 62.5% | **+15pp** |
| Keywords | 72.9% | 58.6% | **+14pp** |
| Structure | 73.2% | 63.8% | **+9pp** |

### Token Savings Detail

Measured on a real codebase (88 files) across 8 tool categories:

| Metric | Value |
|--------|-------|
| Raw tool-level multiplier | 9.87x |
| Balanced workflow (session-net) | 75.9% savings, 4.15x session extension |
| Heavy analysis workflow | 83.0% savings, 5.88x session extension |
| Lean coding workflow | 81.8% savings |

C3's own overhead (800-token mandates, 1,200-token tool schemas, 600-token recalls) is factored into all session-net figures.

### Methodology

Each task runs the same model twice on an identical git worktree sandbox: once with C3 MCP tools, once without. Responses are scored across five deterministic dimensions (keyword, structural, file mention, factual, completeness) using ground-truth evaluation. No cherry-picking, no prompt tuning between runs. Full source code and raw JSON results are included in this repository.

> **What does "pp" mean?** Percentage points. When a score goes from 57% to 82%, that's a +25 percentage point improvement — 25 points on the 0–100 scale.

---

## Compatibility

| Tool | Provider | MCP Tools | Hooks | Instruction Sync | Notes |
|------|----------|-----------|-------|------------------|-------|
| **Claude Code** | Anthropic | Yes | Yes | Yes | Full support — hooks, CLAUDE.md sync, budget management |
| **VS Code** | Microsoft | Yes | — | — | MCP tools via Copilot extension |
| **Codex CLI** | OpenAI | Yes | — | Yes | MCP tools + AGENTS.md + session config |
| **Gemini CLI** | Google | Yes | — | Yes | MCP tools + GEMINI.md + session config |

### MCP Modes

- **Direct** (recommended): Points the IDE straight at `cli/mcp_server.py`. Minimal overhead, maximum reliability.
- **Proxy** (advanced): Dynamic tool filtering via a proxy layer. Useful for teams experimenting with context routing.

### IDE-Specific Install

```bash
c3 install-mcp claude          # Claude Code
c3 install-mcp codex           # Codex CLI
c3 install-mcp . gemini        # Gemini CLI (from project dir)
```

`install-mcp` generates the appropriate config files for each IDE:
- Claude Code: `.mcp.json` + `.claude/settings.local.json` with PostToolUse hooks
- Codex CLI: `.mcp.json` + `.codex/config.toml`
- Gemini CLI: `.mcp.json` + `.gemini/settings.json`

Instruction files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`) are synced into the project root automatically.

---

## Tiered Local AI (Hybrid Intelligence)

When [Ollama](https://ollama.com/) is available, C3 activates a three-tier local intelligence system:

| Tier | Model | Use Case | Latency |
|------|-------|----------|---------|
| **Nano** | `qwen2:0.5b` | Intent classification and routing | <100ms |
| **Micro** | `deepseek-r1:1.5b` | Q&A, summarization, context retrieval | ~500ms |
| **Base** | `llama3.2:3b`+ | Code analysis, technical reasoning | ~2s |

### Optimizations

- **Semantic Caching** — persistent disk-based cache reduces repeat latency to zero
- **Dynamic Context Control** — automatic `num_ctx` right-sizing per task type
- **Real-time Streaming** — token-by-token delivery via SSE for responsive UI

Ollama is optional. All core tools work without it.

---

## Web UI

C3 includes two web dashboards, no extra install required:

### Project Dashboard

```bash
c3 ui /path/to/project [--port 3333]
```

Full-featured web UI for a single project: index health, compression experiments, session management, memory and facts, activity logs, conversation transcripts, hybrid AI tiers, agents, and settings.

### Project Hub

```bash
c3 hub [--port 3330]
```

Global control center for all your C3 projects. Register projects, view health across your portfolio, manage MCP configs, browse sessions, and launch the project UI for any project in one click.

---

## Advanced / Optional

These tools are available but not part of the recommended default:

- Proxy-driven dynamic tool filtering
- `c3_route`, `c3_summarize`, `c3_raw`
- `c3_why_context`, `c3_token_stats`, `c3_context_status`
- `c3_notifications`
- CLAUDE.md lifecycle tools

---

## Notes

- Claude Code hooks enforce large-read and log-read guardrails when installed.
- `--git` runs a local-only `git init` — it does not add remotes or use any hosted service.
- Existing installs are not automatically migrated; rerun `install-mcp` or `init --force` to switch defaults.
- C3 runs entirely locally and does not transmit your code or project data to external servers.

---

## Support C3

C3 is free and open source. If it saves you tokens, extends your sessions, and makes your AI coding workflow better, consider supporting its development.

[![Sponsor on GitHub](https://img.shields.io/badge/sponsor-drknowhow-ea4aaa.svg?logo=github-sponsors&style=for-the-badge)](https://github.com/sponsors/drknowhow)

---

## License

This project is licensed under the [MIT License](LICENSE).

*Created by AI, for AI — via Dr. Know How's hard work.*

---

C3 is provided "as is", without warranty of any kind, express or implied. Token savings, session length improvements, and benchmark figures are based on internal testing — actual results may vary. C3 is not affiliated with, endorsed by, or officially connected to Anthropic, OpenAI, Google, or any AI model provider. The authors are not responsible for any data loss, unexpected behavior, or costs incurred through use of this software.
