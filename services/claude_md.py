"""
CLAUDE.md Management Service

Provides intelligent CLAUDE.md lifecycle tools:
- generate: Create CLAUDE.md from live project data + session/memory insights
- check_staleness: Detect drift between CLAUDE.md and actual project state
- compact: Reduce bloated CLAUDE.md while preserving critical info
- get_promotion_candidates: Surface high-value facts/patterns for inclusion

All methods are read-only — they return content/reports but never write to disk.
"""
import json
import re
from pathlib import Path
from typing import Optional
from core import count_tokens


# Default truncation limit (Claude Code truncates after 200 lines)
TRUNCATION_LIMIT = 200

C3_COMPACT_WORKFLOW = """\
# C3 Tooling Mandate (CRITICAL)
Use `c3_*` tools by default. Native IDE search/read tools are fallback-only.

# Required Workflow
- **START**: Call `c3_memory(action='recall', query='...')` or `c3_memory(action='query', query='...')` before exploring code for tasks that may have prior context.
- **DISCOVER**: Call `c3_search(query='...', action='files|code|semantic')` before broad repo search, file listing, or ad-hoc discovery. Use `action='semantic'` for natural-language queries when TF-IDF keyword search is insufficient.
- **MAP**: Call `c3_compress(file_path='...', mode='map|dense_map')` before reading unfamiliar or large files.
- **READ**: Call `c3_read(file_path='...', symbols=['...']|lines=[[start,end]])` before broad file reads. Use native file reads only for a narrow follow-up after C3 narrowing.
- **DATA**: Call `c3_filter(text='...')` for terminal output over 10 lines and `c3_filter(file_path='...')` before reading log, txt, or jsonl files directly.
- **CHECK**: Prefer `c3_validate(file_path='...')` for time-bounded native syntax validation after edits or before reporting completion.
- **LOG**: Use `c3_session(action='log', event_type='decision', ...)` for important decisions. Use `c3_session(action='snapshot')` before `/clear`.

# Automated Budget Management
- **Budget Monitoring**: Check the token budget (via `c3_status(view='budget')`) at the start of each task.
- **Truncation Detection**: If a tool output contains `[ctx:truncated ... | snapshot→new conversation→restore to reset budget]`, it means the tool response was cut short due to high token usage.
- **Proactive Restart**: If the budget is high (>=80%) or critical (>=90%), or if a **Truncation Detection** occurs, proactively prompt the user after finishing the current turn: "Token budget is [XX]% (and/or truncation occurred). Would you like me to automate a session restart? I will take a snapshot and provide you with a one-click restore command for your new conversation."
- **One-Click Restart**: Upon confirmation:
  1. Call `c3_session(action='snapshot', data='automated_restart', summary='Taking snapshot before session restart')`.
  2. Inform the user: "Snapshot taken. Please run `/clear` and then paste: `c3_session(action='restore', data='latest')` to continue immediately."
- **Self-Preservation**: Prioritize this restart over continuing with a bloated context to avoid tool failures or degradation in AI performance.

# Fallback Rules
- Do not start with native repo search, broad file reads, or raw log reads when a matching `c3_*` tool exists.
- Fallback is allowed only if the C3 tool failed, returned insufficient scope, or a tiny follow-up read is faster than another tool round-trip.
- When falling back, state which C3 tool was attempted or skipped and why.

# Reporting Rules
- Mention the `c3_*` tools used when summarizing work.
- If no C3 tool was used for exploration, say why that exception was necessary.

# Core C3 Tools
- `c3_memory(action='recall'|'query')` for cross-session context and memory retrieval.
- `c3_memory(action='export')` for markdown-formatted facts to paste into MEMORY.md topic files.
- `c3_search(action='files'|'code'|'transcript'|'semantic')` for discovery before native search.
- `c3_compress(mode='map'|'dense_map'|'smart')` for structural overview and token-efficient understanding.
- `c3_read(...)` for surgical symbol or line extraction.
- `c3_filter(...)` for noisy terminal, log, txt, and jsonl input.
- `c3_validate(...)` for deterministic, time-bounded syntax validation when available.
- `c3_session(action='log|plan|snapshot|restore|convo_log')` for decisions and continuity."""


class ClaudeMdManager:
    """Manages instructions file generation, analysis, compaction, and insight promotion.

    Supports multiple IDEs — instructions_file determines the output filename
    (e.g. CLAUDE.md for Claude Code, .github/copilot-instructions.md for VS Code).
    """

    def __init__(self, project_path: str, session_mgr, indexer, memory,
                 instructions_file: str = "CLAUDE.md", line_limit: int = 200,
                 supports_hooks: bool = True, supports_clear: bool = True):
        self.project_path = Path(project_path)
        self.session_mgr = session_mgr
        self.indexer = indexer
        self.memory = memory
        self.instructions_file = instructions_file
        self.line_limit = line_limit
        self.supports_hooks = supports_hooks
        self.supports_clear = supports_clear

    # ── Public API (one per MCP tool) ────────────────────────

    def _build_c3_workflow(self) -> str:
        """Build compact C3 workflow section. Optimized for minimal token footprint."""
        return C3_COMPACT_WORKFLOW

    def generate(self, include_sessions: bool = True) -> dict:
        """Generate token-efficient CLAUDE.md from live project data.

        Optimized for minimal per-turn overhead:
        - Compact C3 tool reference (~7 lines vs ~16)
        - No session history (use c3_memory recall instead)
        - Top 5 learned facts only (rest available via c3_memory)
        - No shortcuts section (low value, costs tokens every turn)
        """
        parts = []

        # C3 workflow instructions (compact)
        parts.append(self._build_c3_workflow())

        # Project structure
        parts.append("\n# Project Context\n")
        parts.append(self.session_mgr._scan_project_structure())

        # Tech stack
        parts.append("\n## Tech Stack\n")
        parts.append(self.session_mgr._detect_tech_stack())

        # Key files (compact)
        key_files = self._detect_key_files()
        if key_files:
            parts.append("\n## Key Files\n")
            for kf in key_files[:5]:
                parts.append(f"- `{kf['file']}` — {kf['reason']}")

        # Top learned facts only (rest available via c3_memory recall)
        promoted_facts = [
            f for f in self.memory.facts
            if f.get("relevance_count", 0) >= 3
        ]
        if promoted_facts:
            parts.append("\n## Key Facts (use c3_memory for more)\n")
            for f in promoted_facts[:5]:
                parts.append(f"- {f['fact'][:120]}")

        content = '\n'.join(parts)
        metrics = self._count_metrics(content)

        return {
            "content": content,
            "lines": metrics["lines"],
            "tokens": metrics["tokens"],
            "truncation_warning": (
                f"Content is {metrics['lines']} lines — truncation may occur after {self.line_limit}. "
                "Use CLI `c3 claudemd compact` to reduce."
            ) if self.line_limit and metrics["lines"] > self.line_limit else None,
        }

    def check_staleness(self) -> dict:
        """Check existing CLAUDE.md for staleness and drift."""
        current = self._read_current()
        if current is None:
            return {
                "status": "missing",
                "issues": [{
                    "severity": "error",
                    "message": f"No {self.instructions_file} found. Use CLI `c3 claudemd generate` to create one.",
                }],
            }

        issues = []
        sections = self._parse_sections(current)
        metrics = self._count_metrics(current)

        # Size warning (only if line_limit is set)
        if self.line_limit and metrics["lines"] > self.line_limit:
            issues.append({
                "severity": "warning",
                "message": (
                    f"{self.instructions_file} is {metrics['lines']} lines ({metrics['tokens']} tokens). "
                    f"Truncation may occur after {self.line_limit} lines. "
                    "Use CLI `c3 claudemd compact` to reduce."
                ),
            })

        # Structure drift
        structure_issues = self._diff_structure(current)
        issues.extend(structure_issues)

        # Tech stack drift
        tech_issues = self._diff_tech_stack(current)
        issues.extend(tech_issues)

        # Session staleness
        session_files = sorted(
            (self.project_path / ".c3" / "sessions").glob("session_*.json"),
            reverse=True,
        ) if (self.project_path / ".c3" / "sessions").exists() else []

        session_section = sections.get("Session History (Compressed)", "")
        if session_files:
            # Count sessions mentioned in CLAUDE.md
            mentioned_ids = set(re.findall(r'Session:\s*(\d{8}_\d{6})', session_section))
            total_sessions = len(session_files)
            unmentioned = total_sessions - len(mentioned_ids)
            if unmentioned > 3:
                issues.append({
                    "severity": "info",
                    "message": f"{unmentioned} sessions not reflected in CLAUDE.md. Consider regenerating.",
                })

        if not issues:
            issues.append({
                "severity": "info",
                "message": "CLAUDE.md looks up to date.",
            })

        return {
            "status": "ok" if all(i["severity"] == "info" for i in issues) else "stale",
            "lines": metrics["lines"],
            "tokens": metrics["tokens"],
            "issues": issues,
        }

    def compact(self, target_lines: int = 150) -> dict:
        """Compact existing CLAUDE.md to fit within target line count."""
        current = self._read_current()
        if current is None:
            return {"error": f"No {self.instructions_file} found on disk. Use CLI `c3 claudemd generate` to preview, then `c3 claudemd save` to persist before compacting."}

        original_metrics = self._count_metrics(current)
        sections = self._parse_sections(current)
        lines = current.split('\n')

        # If already under target, no compaction needed
        if original_metrics["lines"] <= target_lines:
            return {
                "content": current,
                "original_lines": original_metrics["lines"],
                "compacted_lines": original_metrics["lines"],
                "original_tokens": original_metrics["tokens"],
                "compacted_tokens": original_metrics["tokens"],
                "actions": ["Already under target — no compaction needed."],
            }

        actions = []

        # Step 1: Compress session history — keep last 3, one-line summaries
        if "Session History (Compressed)" in sections:
            session_text = sections["Session History (Compressed)"]
            compressed = self._compress_sessions(session_text, max_sessions=3)
            if len(compressed.split('\n')) < len(session_text.split('\n')):
                sections["Session History (Compressed)"] = compressed
                actions.append("Trimmed session history to last 3 sessions with one-line summaries")

        # Step 2: Deduplicate — remove exact duplicate lines (excluding blank lines and headers)
        seen_lines = set()
        deduped_sections = {}
        for name, text in sections.items():
            if name in ("User Notes", "C3 — Token-Saving Workflow (MUST FOLLOW)"):
                deduped_sections[name] = text
                continue
            new_lines = []
            for line in text.split('\n'):
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    new_lines.append(line)
                elif stripped not in seen_lines:
                    seen_lines.add(stripped)
                    new_lines.append(line)
            deduped_sections[name] = '\n'.join(new_lines)
        dup_removed = sum(
            len(sections[k].split('\n')) - len(deduped_sections[k].split('\n'))
            for k in sections
        )
        if dup_removed > 0:
            actions.append(f"Removed {dup_removed} duplicate lines")
            sections = deduped_sections

        # Step 3: Prune structure tree depth if still over target
        content = self._reassemble_sections(sections)
        current_lines = len(content.split('\n'))
        if current_lines > target_lines and "Project Context (Auto-generated by C3)" in sections:
            ctx_section = sections["Project Context (Auto-generated by C3)"]
            pruned = self._prune_structure_depth(ctx_section, max_depth=2)
            if len(pruned.split('\n')) < len(ctx_section.split('\n')):
                sections["Project Context (Auto-generated by C3)"] = pruned
                actions.append("Reduced project structure tree depth")

        # Reassemble
        content = self._reassemble_sections(sections)
        compacted_metrics = self._count_metrics(content)

        if not actions:
            actions.append("No compaction opportunities found.")

        return {
            "content": content,
            "original_lines": original_metrics["lines"],
            "compacted_lines": compacted_metrics["lines"],
            "original_tokens": original_metrics["tokens"],
            "compacted_tokens": compacted_metrics["tokens"],
            "actions": actions,
        }

    def get_promotion_candidates(self, min_relevance: int = 2) -> dict:
        """Find facts and patterns worth promoting into CLAUDE.md."""
        current = self._read_current()
        current_text = current or ""
        candidates = {
            "Code Patterns & Conventions": [],
            "Quick Reference Shortcuts": [],
            "Key Files": [],
            "Project Roadmap & Active Plans": [],
        }

        # High-relevance facts
        for fact in self.memory.facts:
            if fact.get("relevance_count", 0) < min_relevance:
                continue
            # Skip if already in CLAUDE.md
            if fact["fact"] in current_text:
                continue

            category = fact.get("category", "general")
            target = "Code Patterns & Conventions"
            if category in ("shortcut", "reference", "alias"):
                target = "Quick Reference Shortcuts"
            elif category in ("file", "path", "entry_point"):
                target = "Key Files"
            elif category in ("plan", "roadmap", "todo"):
                target = "Project Roadmap & Active Plans"

            candidates[target].append({
                "fact": fact["fact"],
                "category": category,
                "relevance_count": fact["relevance_count"],
                "snippet": f"- [{category}] {fact['fact']}",
            })

        # Recurring decisions and plans from sessions
        session_dir = self.project_path / ".c3" / "sessions"
        if session_dir.exists():
            decision_keywords = {}  # keyword -> [session_ids]
            active_plans = []  # List of unique plan strings
            for sf in sorted(session_dir.glob("session_*.json"), reverse=True)[:20]:
                try:
                    with open(sf) as f:
                        s = json.load(f)
                    sid = s.get("id", "unknown")
                    for d in s.get("decisions", []):
                        text = d.get("decision", "")
                        # Plan detection
                        if "PLAN:" in text.upper():
                            plan_text = text.split("PLAN:", 1)[1].strip()
                            if plan_text and not any(p["fact"] == plan_text for p in active_plans):
                                active_plans.append({
                                    "fact": plan_text,
                                    "category": "active_plan",
                                    "relevance_count": 1,
                                    "snippet": f"- [PLAN] {plan_text}"
                                })
                        
                        # Decision keyword extraction (5+ chars)
                        words = set(re.findall(r'[a-zA-Z]{5,}', text.lower()))
                        for w in words:
                            if w not in decision_keywords:
                                decision_keywords[w] = []
                            if sid not in decision_keywords[w]:
                                decision_keywords[w].append(sid)
                except Exception:
                    continue

            # Add unique plans to roadmap
            for p in active_plans:
                if p["fact"] not in current_text:
                    candidates["Project Roadmap & Active Plans"].append(p)

            # Keywords appearing in 2+ sessions
            recurring = {k: v for k, v in decision_keywords.items() if len(v) >= 2}
            for keyword, session_ids in sorted(recurring.items(), key=lambda x: -len(x[1]))[:5]:
                snippet = f"- Recurring decision keyword: \"{keyword}\" (across {len(session_ids)} sessions)"
                if snippet not in current_text:
                    candidates["Code Patterns & Conventions"].append({
                        "fact": f"Recurring decision keyword: \"{keyword}\"",
                        "category": "recurring_decision",
                        "relevance_count": len(session_ids),
                        "snippet": snippet,
                    })

        # Filter out empty groups
        candidates = {k: v for k, v in candidates.items() if v}

        total = sum(len(v) for v in candidates.values())
        return {
            "total_candidates": total,
            "candidates": candidates,
            "message": (
                f"Found {total} promotion candidates across {len(candidates)} sections."
                if total > 0
                else "No promotion candidates found. Build more session history and facts first."
            ),
        }

    # ── Shared helpers ───────────────────────────────────────

    def _read_current(self) -> Optional[str]:
        """Read existing instructions file from project root."""
        path = self.project_path / self.instructions_file
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _parse_sections(self, content: str) -> dict:
        """Split CLAUDE.md into named sections by # or ## headers."""
        sections = {}
        current_name = "_preamble"
        current_lines = []

        for line in content.split('\n'):
            header_match = re.match(r'^(#{1,3})\s+(.+)', line)
            if header_match:
                # Save previous section
                if current_lines or current_name != "_preamble":
                    sections[current_name] = '\n'.join(current_lines)
                current_name = header_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Save last section
        if current_lines or current_name != "_preamble":
            sections[current_name] = '\n'.join(current_lines)

        return sections

    def _reassemble_sections(self, sections: dict) -> str:
        """Reassemble sections into CLAUDE.md content."""
        parts = []
        for name, body in sections.items():
            if name == "_preamble":
                if body.strip():
                    parts.append(body)
            else:
                # Determine header level from body context (default ##)
                level = "#"
                if name in ("Project Context (Auto-generated by C3)",
                            "Session History (Compressed)", "User Notes"):
                    level = "#"
                else:
                    level = "##"
                parts.append(f"{level} {name}\n{body}")
        return '\n\n'.join(parts)

    def _count_metrics(self, content: str) -> dict:
        """Count lines and tokens."""
        lines = len(content.split('\n'))
        tokens = count_tokens(content)
        return {"lines": lines, "tokens": tokens}

    # ── Generate helpers ─────────────────────────────────────

    def _detect_enhanced_patterns(self) -> list:
        """Detect patterns beyond what SessionManager finds — linting, test frameworks, monorepo."""
        patterns = []
        p = self.project_path

        # Base patterns from session manager
        base = self.session_mgr._detect_patterns()
        if base and base != "No patterns auto-detected":
            for line in base.split('\n'):
                line = line.strip().lstrip('- ')
                if line:
                    patterns.append(line)

        # Linting / formatting
        linting_indicators = {
            ".eslintrc": "ESLint", ".eslintrc.js": "ESLint", ".eslintrc.json": "ESLint",
            ".eslintrc.yml": "ESLint", "eslint.config.js": "ESLint (flat config)",
            ".prettierrc": "Prettier", ".prettierrc.json": "Prettier",
            "prettier.config.js": "Prettier",
            ".flake8": "Flake8", "setup.cfg": "Python config (setup.cfg)",
            "ruff.toml": "Ruff", ".ruff.toml": "Ruff",
            ".stylelintrc": "Stylelint",
            "biome.json": "Biome",
        }
        for filename, tool in linting_indicators.items():
            if (p / filename).exists():
                patterns.append(f"Uses {tool}")

        # Check pyproject.toml for tool configs
        pyproject = p / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text(encoding="utf-8")
                if "[tool.ruff" in text:
                    patterns.append("Uses Ruff (via pyproject.toml)")
                if "[tool.black" in text:
                    patterns.append("Uses Black formatter")
                if "[tool.pytest" in text or "[tool.pytest.ini_options" in text:
                    patterns.append("Uses pytest")
                if "[tool.mypy" in text:
                    patterns.append("Uses mypy type checking")
            except Exception:
                pass

        # Test frameworks
        if (p / "jest.config.js").exists() or (p / "jest.config.ts").exists():
            patterns.append("Uses Jest for testing")
        if (p / "vitest.config.ts").exists() or (p / "vitest.config.js").exists():
            patterns.append("Uses Vitest for testing")
        if (p / "pytest.ini").exists() or (p / "conftest.py").exists():
            patterns.append("Uses pytest")

        # Monorepo indicators
        if (p / "lerna.json").exists():
            patterns.append("Monorepo (Lerna)")
        if (p / "pnpm-workspace.yaml").exists():
            patterns.append("Monorepo (pnpm workspaces)")
        if (p / "turbo.json").exists():
            patterns.append("Monorepo (Turborepo)")
        pkg = p / "package.json"
        if pkg.exists():
            try:
                with open(pkg) as f:
                    data = json.load(f)
                if "workspaces" in data:
                    patterns.append("Monorepo (npm/yarn workspaces)")
            except Exception:
                pass

        # Deduplicate
        seen = set()
        unique = []
        for pat in patterns:
            key = pat.lower()
            if key not in seen:
                seen.add(key)
                unique.append(pat)

        return unique

    def _detect_key_files(self) -> list:
        """Identify key files from session history and conventional entry points."""
        key_files = []
        seen = set()

        # Hot files from session history
        session_dir = self.project_path / ".c3" / "sessions"
        if session_dir.exists():
            file_counts = {}
            for sf in sorted(session_dir.glob("session_*.json"), reverse=True)[:20]:
                try:
                    with open(sf) as f:
                        s = json.load(f)
                    for ft in s.get("files_touched", []):
                        fname = ft.get("file", "")
                        if fname:
                            file_counts[fname] = file_counts.get(fname, 0) + 1
                except Exception:
                    continue

            for fname, count in sorted(file_counts.items(), key=lambda x: -x[1])[:5]:
                if count >= 2 and fname not in seen:
                    key_files.append({"file": fname, "reason": f"edited in {count} sessions"})
                    seen.add(fname)

        # Conventional entry points
        entry_points = [
            ("main.py", "Python entry point"),
            ("app.py", "Application entry point"),
            ("index.ts", "TypeScript entry point"),
            ("index.js", "JavaScript entry point"),
            ("src/index.ts", "Source entry point"),
            ("src/index.js", "Source entry point"),
            ("src/main.ts", "Source entry point"),
            ("src/App.tsx", "React app root"),
            ("cli/mcp_server.py", "MCP server entry"),
        ]
        for filepath, reason in entry_points:
            if (self.project_path / filepath).exists() and filepath not in seen:
                key_files.append({"file": filepath, "reason": reason})
                seen.add(filepath)

        return key_files

    # ── Check helpers ────────────────────────────────────────

    def _diff_structure(self, current_content: str) -> list:
        """Find dirs mentioned in CLAUDE.md that don't exist, and new dirs not mentioned."""
        issues = []

        # Extract dir-like references from the code block
        mentioned_dirs = set()
        in_code_block = False
        for line in current_content.split('\n'):
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            if in_code_block and line.strip().endswith('/'):
                dirname = line.strip().rstrip('/')
                if dirname:
                    mentioned_dirs.add(dirname)

        # Scan actual top-level dirs
        skip = {'node_modules', '.git', '__pycache__', '.c3', 'venv',
                'env', '.venv', 'dist', 'build', '.next', '.cache', '.claude'}
        actual_dirs = set()
        for item in self.project_path.iterdir():
            if item.is_dir() and item.name not in skip and not item.name.startswith('.'):
                actual_dirs.add(item.name)

        # Compare (use base names only)
        mentioned_basenames = {d.split('/')[-1] for d in mentioned_dirs if d}

        missing_in_fs = mentioned_basenames - actual_dirs
        new_in_fs = actual_dirs - mentioned_basenames

        for d in missing_in_fs:
            # Skip the project root name
            if d == self.project_path.name:
                continue
            issues.append({
                "severity": "warning",
                "message": f"Directory '{d}' mentioned in CLAUDE.md but not found on disk.",
            })

        for d in new_in_fs:
            issues.append({
                "severity": "info",
                "message": f"New directory '{d}' exists but is not in CLAUDE.md.",
            })

        return issues

    def _diff_tech_stack(self, current_content: str) -> list:
        """Compare tech stack in CLAUDE.md vs detected."""
        issues = []
        detected = self.session_mgr._detect_tech_stack()

        if detected == "Could not auto-detect":
            return issues

        detected_set = {t.strip().lower() for t in detected.split(',')}

        # Find the tech stack line in CLAUDE.md
        sections = self._parse_sections(current_content)
        claimed_text = sections.get("Tech Stack", "")
        claimed_set = set()
        for line in claimed_text.split('\n'):
            line = line.strip().lstrip('- ')
            if line:
                for item in line.split(','):
                    item = item.strip().lower()
                    if item:
                        claimed_set.add(item)

        new_tech = detected_set - claimed_set
        for tech in new_tech:
            issues.append({
                "severity": "warning",
                "message": f"Detected '{tech}' in project but not listed in CLAUDE.md Tech Stack.",
            })

        return issues

    # ── Compact helpers ──────────────────────────────────────

    def _compress_sessions(self, session_text: str, max_sessions: int = 3) -> str:
        """Trim session history to last N sessions with one-line summaries."""
        # Split into individual session blocks (## Session: ...)
        blocks = re.split(r'(?=## Session:)', session_text)
        blocks = [b.strip() for b in blocks if b.strip()]

        if len(blocks) <= max_sessions:
            return session_text

        # Keep only last max_sessions, compress each to one line
        kept = blocks[:max_sessions]
        compressed_lines = []
        for block in kept:
            lines = block.split('\n')
            header = lines[0] if lines else ""
            # Extract summary if present
            summary = ""
            for line in lines[1:]:
                if line.startswith("**Summary:**"):
                    summary = line.replace("**Summary:**", "").strip()
                    break
                elif line.startswith("**When:**"):
                    date = line.replace("**When:**", "").strip()
                    summary = f"({date}) {summary}"
            if summary:
                compressed_lines.append(f"{header}\n**Summary:** {summary}\n")
            else:
                compressed_lines.append(f"{header}\n")

        return '\n'.join(compressed_lines)

    def _prune_structure_depth(self, section_text: str, max_depth: int = 2) -> str:
        """Reduce project structure tree depth."""
        lines = section_text.split('\n')
        pruned = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                pruned.append(line)
                continue

            if in_code_block:
                # Count indent level (2 spaces per level)
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                depth = indent // 2
                if depth <= max_depth:
                    pruned.append(line)
            else:
                pruned.append(line)

        return '\n'.join(pruned)
