# Agent Execution Protocol

All AI coding assistants and autonomous agents operating in this workspace must strictly adhere to this protocol.

## 1. Core Principles

1. **Analysis Before Action**: Thoroughly analyze the request, existing codebase, and architectural context before implementing any feature, spec change, or bug fix.
2. **PRD as Single Source of Truth**: Update `./PRD.md` before changing code whenever a request impacts product features, requirements, data schemas, or business behavior.
3. **Explicit User Approval**: Always pause and request explicit user confirmation after updating `./PRD.md`. Do NOT touch source code without approval.
4. **Defensive Implementation**: Validate changes with tests, builds, and lint checks. Never run destructive terminal commands without confirmation.
5. **Clear Review & Release**: Share structured summaries of changes and follow Conventional Commits for all git operations.

---

## 2. 5-Step Execution Workflow

```
[Step 1: Analyze] ──> [Step 2: Update PRD] ──> [Step 3: User Approval] ──> [Step 4: Implement & Verify] ──> [Step 5: Review & Commit]
```

### Step 1: Analyze
- Classify request (`Feature`, `Bug Fix`, `Refactor`, `Spec Change`, `Chore`) and identify affected files/APIs/dependencies.
- **Propose Directions**: Think deeply on trade-offs and propose 2–3 architectural directions to the user (via `ask_question`).
- **Docs & Questions**: Validate unfamiliar APIs in official docs/MCP without guessing; clarify ambiguous requirements promptly.

### Step 2: Update PRD
- Update `./PRD.md` according to the selected direction (background, requirements, priority, data/API schema, acceptance criteria).
- **Exceptions**: Minor styling, trivial bug fixes, and typos can bypass PRD updates.
- *(Release history is tracked exclusively in `CHANGELOG.md`)*

### Step 3: Get User Approval
- Share updated PRD highlights and **pause until explicit user approval before touching code**.

### Step 4: Implement & Verify
- **Multi-Agent Pipeline (`rules/multi-agent.md`)**:
  - Lead PM delegates feature coding to subagents via `invoke_subagent`.
  - **UI Tasks**: Dispatch `frontend-agent`(`ui-ux-pro-max`, `seo`) + `ui-auditor` ➔ Output screenshot artifact ➔ **Halt and wait for user screen approval**.
  - **Headless/Backend**: After screen approval, dispatch `backend-agent`(`tdd`) + `tester` ➔ Validate all green. Trigger `code-reviewer` every 3rd commit.
- **TDD Cycle**: Red (failing test) ➔ Green (minimal code) ➔ Refactor.
- **Comments & Sync**: Write Korean comments on functions/constants; sync bilingual rule changes simultaneously.

### Step 5: Final Review & Commit
- **Single Instruction & Immediate Halt**: After user confirmation, commit atomically on `dev` in Korean Conventional Commits and **halt immediately**.
- **Decoupled Steps**: A commit approval NEVER implies merge or push; each stage requires separate explicit instructions.
- Write Korean release notes in `CHANGELOG.md` when merging into `main`.

---

## 3. Fast-Track Exceptions
- Minor styling tweaks, simple bug fixes, typos, and read-only searches bypass PRD updates and proceed immediately.

---

## 4. Batch & Long-Running Task Discipline (Anti-Hang Protocol)

1. **Benchmark Before Full Run**: Before launching large batch jobs (scraping, heavy backtesting, ETL), run a micro-benchmark (5–10 samples) to measure throughput per unit and compute projected total duration (ETA).
2. **Explicit Checkpoints & Timeout**: Never allow unattended background tasks. Set tight timeout checks and periodic progress checkpoints.
3. **Bottleneck Detection & Fast-Halt**: If processing throughput degrades or will exceed reasonable operational limits, immediately halt execution, report root cause analysis, and propose architectural fixes (e.g., bulk APIs, concurrency) rather than idle waiting.


