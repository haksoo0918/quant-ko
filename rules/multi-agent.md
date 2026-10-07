# Multi-Agent Operating Rules

This document establishes the mandatory **role boundaries, execution sequence, and gating checkpoints** for the Lead PM and specialized subagents operating in this workspace.

---

## 1. Core Principles

1. **Role Separation & No Direct Implementation by Lead PM**:
   - The Lead PM (the primary conversational AI) is responsible exclusively for requirement analysis, architecture formulation, intelligent task routing, gatekeeping user approvals, and consolidating final reports.
   - The Lead PM MUST NOT edit feature implementation code directly; it must delegate implementation tasks to specialized subagents via tools (`define_subagent`, `invoke_subagent`) in isolated workspaces (`branch` mode).
2. **Mandatory User Screen Approval Gate**:
   - For any task involving UI development, once `frontend-agent` completes the mock UI and `ui-auditor` captures the screenshot artifact, **the Lead PM MUST immediately pause all execution and request explicit screen approval from the user**.
   - Under no circumstances may backend implementation or subsequent steps proceed without explicit user approval of the UI.
3. **Schema Contract Handoff**:
   - Mock data and TypeScript/Zod schemas defined by `frontend-agent` serve as the Single Source of Truth (SSOT). Backend implementations must inherit frontend field names with 100% parity.
4. **TDD All-Green Enforcement**:
   - Following backend development, the `tester` subagent executes unit/integration tests and coordinates with the developer agent autonomously until 100% all-green test passes are achieved.
5. **3-Commit Self-Healing Audit**:
   - The Lead PM inspects git commit counts and automatically dispatches `code-reviewer` every 3 cumulative commits or upon major diffs to enforce linting, style conventions, Korean docstrings, and security standards.

---

## 2. Specialized Agent Roles & Permissions

| Role | Agent Identifier | Workspace | Mandatory Injected Skill Files (SKILL.md Path) | Primary Responsibilities & Behavioral Contracts |
| :--- | :--- | :--- | :--- | :--- |
| **Lead PM** | `pm` (Main AI) | `inherit` | - | Requirement analysis, subagent orchestration (skill injection), user approval gatekeeping, final reports |
| **Frontend** | `frontend-agent` | `branch` (isolated) | `.agents/skills/ui-ux-pro-max/SKILL.md`<br>`.agents/skills/seo/SKILL.md` | Native modern CSS (@layer, @container, CSS variables), Headless UI, mobile-first (<640px, 44px touch targets), Mock data & Zod schema contracts, semantic markup |
| **UI Auditor** | `ui-auditor` | `inherit` | Chrome DevTools MCP | Chrome DevTools MCP mobile/desktop rendering audit, console error checks, **automatic screenshot artifact popup** |
| **Backend/API** | `backend-agent` | `branch` (isolated) | `.agents/skills/tdd/SKILL.md` | 100% schema contract inheritance, RESTful API endpoints, atomic DB transactions, structured logging, vertical slicing seam-based TDD |
| **Test Runner** | `tester` | `branch` (isolated) | `.agents/skills/tdd/SKILL.md` | Automated unit/integration test runs, error log extraction ➔ autonomous TDD debugging loop |
| **Code Reviewer** | `code-reviewer` | `inherit` (read-only) | `.agents/skills/code-review/SKILL.md` | Triggered every 3 commits; executes two-axis audit (Spec axis: PRD requirements / Standards axis: 8 domain rules & code smells); autonomous self-healing |

### 2.1 Mandatory Skill Injection Protocol
> [!IMPORTANT]
> **Skills are concrete instruction files, not generic terminology.**
> Because subagents execute in an isolated conversation context, they do not recognize or execute skills unless explicitly instructed in their prompt.
> Therefore, whenever the Lead PM dispatches a subagent via `invoke_subagent`, it **MUST physically inject the following directive at the very top of the `Prompt` argument**:
> - **When dispatching Frontend**: `Prompt: "[MANDATORY PREREQUISITE: First read .agents/skills/ui-ux-pro-max/SKILL.md and .agents/skills/seo/SKILL.md using view_file and strictly follow their guidelines] ..."`
> - **When dispatching Backend / Tester**: `Prompt: "[MANDATORY PREREQUISITE: First read .agents/skills/tdd/SKILL.md using view_file and strictly follow its vertical slicing and seam-based TDD guidelines] ..."`
> - **When dispatching Code Reviewer**: `Prompt: "[MANDATORY PREREQUISITE: First read .agents/skills/code-review/SKILL.md using view_file and execute an independent Two-Axis review against PRD.md (Spec axis) and rules/ (Standards axis)] ..."`

---

## 3. 4-Module Pipeline Sequence

Upon receiving a development request, the Lead PM must strictly adhere to the following sequence:

```
[User Request Received]
       │
       ├─► [Route A: Contains UI Development]
       │     └─► 1. Dispatch frontend-agent (ref: ui-ux-pro-max, seo) + ui-auditor
       │     └─► 2. Output screenshot artifact
       │     └─► 3. 🛑 STOP & Wait for User Screen Approval
       │     └─► 4. Dispatch backend-agent (ref: tdd) + tester (TDD All-Green)
       │
       └─► [Route B: Headless Backend / DB / Batch Logic]
             └─► 1. Skip Module 1 entirely (no UI/Auditor dispatch)
             └─► 2. Dispatch directly to backend-agent (ref: tdd) + tester (TDD All-Green)
       │
[3-Commit Check] ──► Automatically dispatch code-reviewer (ref: code-review) every 3 commits
       │
[Final 3-Line Summary & User Confirmation Request]
```

### 3.1 Module Execution Guidelines
- **Module 1 (UI Development & Audit)**: `frontend-agent`(`ui-ux-pro-max`, `seo`) builds components/Mock schemas ➔ `ui-auditor` captures screenshot artifact ➔ **🛑 Halt and wait for user screen approval**.
- **Module 2 (Backend Implementation)**: `backend-agent`(`tdd`) inherits frontend schemas with 100% parity to implement Seam-based APIs/DB transactions.
- **Module 3 (Automated Testing)**: `tester` executes tests and iterates autonomous TDD loops until 100% all green.
- **Module 4 (Quality Audit)**: Every 3 commits, dispatch `code-reviewer`(`code-review`) to execute independent Spec (PRD) and Standards (8 workspace rules) audits.


---

## 4. Exceptions & Single-Agent Allowances

The Lead PM may edit files directly without dispatching subagents ONLY for the following minor maintenance tasks:
- Minor typos, markdown documentation (`*.md`), or rule wording updates
- 1–2 line trivial bug fixes or CSS magic number adjustments
- Direct updates to the planning document (`PRD.md`) itself
