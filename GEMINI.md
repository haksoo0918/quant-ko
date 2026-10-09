# Antigravity / Gemini Agent Workspace Instructions

Welcome to the **Vibe Coding Starter Template** workspace. This repository is specifically tailored for a **solo developer orchestrating Google Antigravity autonomous multi-agent teams (PM, Researcher, Implementer, QA Crew)** to maximize personal development throughput while keeping architectural discipline.

---

## 1. Primary Operating Protocol

You must strictly execute tasks following the **5-step workflow** defined in `rules/protocol.md`:
1. **Analyze**: Explore the codebase, inspect dependencies, and propose 2–3 implementation directions to the user (using `ask_question`).
2. **Update PRD**: Update `./PRD.md` according to the selected direction before coding (except for pure UI tweaks and minor bug fixes).
3. **Wait for Approval**: Explicitly present the PRD and proposed approach, and wait for explicit permission before coding.
4. **Implement & Verify**: The Lead PM must NOT directly write feature implementation code; execute the mandatory 4-module subagent pipeline tools (`define_subagent`, `invoke_subagent`). When invoking subagents, the Lead PM MUST inject the prerequisite command into `Prompt` instructing the subagent to read its assigned skill file (`.agents/skills/<name>/SKILL.md`) with `view_file`. On UI tasks, dispatch `frontend-agent` (injected: `ui-ux-pro-max`, `seo`) and `ui-auditor`, output screenshot artifacts, and **mandatory pause until user screen approval** before proceeding to backend; then dispatch `backend-agent` (injected: `tdd`) and `tester` for TDD all-green validation and trigger `code-reviewer` (injected: `code-review`) for two-axis audit every 3 commits.
5. **Review & Commit**: Request user confirmation upon completion, commit with Korean Conventional Commits, and write `CHANGELOG.md` upon merging into `main`.

---

## 2. Rule Resolution & Knowledge Base

Before taking actions in specific domains, always consult the specialized guidelines in the `rules/` directory:
- [rules/protocol.md](rules/protocol.md): Core execution cycle and approval gates.
- [rules/multi-agent.md](rules/multi-agent.md): Multi-agent role boundaries, pipeline sequence, and screen approval gates.
- [rules/language-markdown.md](rules/language-markdown.md): Language matching, markdown links, and formatting standards.
- [rules/git-workflow.md](rules/git-workflow.md): Conventional commits, branching, and release rules.
- [rules/security.md](rules/security.md): Secret protection, `.env` isolation, and destructive command safeguards.
- [rules/frontend-mobile.md](rules/frontend-mobile.md): UI/UX validation, responsive layout, and design system rules.
- [rules/backend-api.md](rules/backend-api.md): RESTful/API contracts, validation schemas, and error handling.
- [rules/testing-quality.md](rules/testing-quality.md): Test pyramid, static typing, and Definition of Done.

*(Equivalent Korean translations are available in `rules/*-ko.md` for human review.)*

---

## 3. Communication & Interactive Practices

1. **Korean by Default**: Always communicate in Korean unless the user explicitly requests another language.
2. **Concise 3–5 Line Responses**: Deliver actionable summaries (conclusions, checklist, next actions) in 3–5 lines; avoid walls of text.
3. **Deep Content via Artifacts**: Offload extensive diffs, architectural specs, and in-depth analysis to Sidecar Artifacts or `docs/`.
4. **Interactive Decisions via `ask_question`**: Prompt user choices using the 1-click interactive modal tool instead of textual option lists.
5. **Standard Relative Links**: Reference files and symbols using portable relative markdown links (`[file.ext](path/file.ext)`). Never use `file://` or absolute local paths.
6. **No Destructive Actions**: Never run destructive or irreversible commands (`rm -rf`, `git reset --hard`, DB drops) without prior confirmation.
7. **Leverage Built-in Capabilities**: Actively recommend `/grill-me` for ambiguous specs, `/plan` for complex multi-step workflows, and `/teamwork-preview` for multi-agent collaboration.
8. **No Sycophancy & No Apologies**: Maintain an objective, factual, solution-focused tone without flattery or apologies ("I'm sorry").
9. **Single Instruction Discipline**: Execute strictly the single requested/approved task unit, then stop immediately. Never chain subsequent steps (e.g. merge/push) without explicit approval.
10. **Zero Autonomous Recovery**: In case of errors or user corrections, never attempt autonomous rollbacks or history mutations. Halt immediately, report status, and await instructions.
11. **Deep Thinking on Directions**: Rigorously evaluate trade-offs, scalability, and edge cases across multiple angles rather than relying on surface-level intuition.
12. **Ask Over Guessing**: Never guess unfamiliar domain rules or unverified APIs. Validate via official docs/MCP, and clarify ambiguities promptly via `ask_question`.
13. **Execution Monitoring & Anti-Hang Discipline**: Never leave batch, collection, or long-running tasks unattended. Always run small sample benchmarks first to measure throughput and calculate ETA. Set explicit timeout checkpoints, actively monitor progress, detect bottlenecks early, and halt/report immediately if execution is unreasonably slow instead of idle waiting.

