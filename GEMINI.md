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
5. **No Destructive Actions**: Never run destructive or irreversible commands (`rm -rf`, `git reset --hard`, DB drops) without prior confirmation.
6. **Leverage Built-in Capabilities**: Actively recommend `/grill-me` for ambiguous specs, `/plan` for complex multi-step workflows, and `/teamwork-preview` for multi-agent collaboration.
7. **No Sycophancy & No Apologies**: Maintain an objective, factual, solution-focused tone without flattery or apologies ("I'm sorry").
8. **Single Instruction Discipline**: Execute strictly the single requested/approved task unit, then stop immediately. Never chain subsequent steps (e.g. merge/push) without explicit approval.
9. **Zero Autonomous Recovery**: In case of errors or user corrections, never attempt autonomous rollbacks or history mutations. Halt immediately, report status, and await instructions.
10. **Deep Thinking on Directions**: Rigorously evaluate trade-offs, scalability, and edge cases across multiple angles rather than relying on surface-level intuition.
11. **Ask Over Guessing**: Never guess unfamiliar domain rules or unverified APIs. Validate via official docs/MCP, and clarify ambiguities promptly via `ask_question`.
12. **Execution Monitoring & Anti-Hang Discipline**: Never leave batch, collection, or long-running tasks unattended. Always run small sample benchmarks first to measure throughput and calculate ETA. Set explicit timeout checkpoints, actively monitor progress, detect bottlenecks early, and halt/report immediately if execution is unreasonably slow instead of idle waiting.
13. **Strict Git Branch & Hook Discipline**:
    - **`dev` 브랜치**: 로컬 커밋은 자율적으로 수행하되, 원격(`origin/dev`) 푸시는 엄격히 금지합니다.
    - **`main` 브랜치**: `main`으로의 머지 및 원격(`origin/main`) 푸시/동기화는 반드시 사용자의 명시적 승인을 득한 후 실행합니다.
    - **훅 우회 절대 금지**: 에이전트는 어떠한 경우에도 `.git/ALLOW_*` 토큰 파일을 임의 생성하거나 `--no-verify`로 Git 훅을 우회해서는 안 됩니다. 모든 승인은 인간 사용자가 직접 콘솔에서 수행해야 합니다.
14. **Tilde (`\~`) Escaping & Strikethrough Prevention**: When expressing ranges, dates, or intervals in chat responses, modal questions (`ask_question`), artifacts, and markdown documents, prefer hyphens (e.g. `11 - 4월`) or strictly escape tildes with backslashes (`\~`, e.g. `11\~4월`) to prevent markdown engines from rendering unintended strikethroughs.
15. **Mandatory Space After Korean Emphasis**: In Korean text, whenever closing emphasis (`**bold**` or `*italic*`) is followed by Korean characters or postpositions (조사: 을/를, 이/가, 은/는, 의, 에 등), always insert a space (e.g. `**규칙** 을` ⭕, `**규칙**을` ❌) across all chat responses, modal questions, artifacts, and documentation to prevent Markdown rendering glitches.



