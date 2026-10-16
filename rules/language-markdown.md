# Language & Markdown Standards

This document establishes the communication, formatting, and documentation guidelines for all AI agents and contributors in this workspace.

## 1. Natural Language Guidelines

1. **Strict Korean for Responses**: Always reply in Korean for all agent communications, technical explanations, summaries, and user interactions.
2. **Strict Korean for Code Comments**: All source code comments, inline annotations, function docstrings, and architectural remarks within code must be written in Korean.
3. **Mandatory Korean Comments for Constants and Functions**: All core constants and functions/methods declared in source files must have Korean docstrings or comments explaining their purpose, parameters, return values, and business context.
4. **Commit Messages in Korean**: All commit messages, types, scopes, and summaries must be written in Korean (following `rules/git-workflow.md`).
5. **Code Identifiers in English**: Programming language identifiers (variable names, function names, types, interfaces, filenames, branch names) remain in English standard idioms (camelCase, PascalCase, kebab-case) for compiler compatibility.
6. **Concise & High-Signal Agent Rules**:
   - When drafting or editing agent guidelines (`GEMINI.md`, `rules/*`), eliminate background narratives, fluff, and redundant commentary.
   - To preserve LLM attention and token efficiency, **write strictly in clear, imperative constraints (Do & Don't) and high-density bullet points**.
   - Compress each rule to 1–2 lines focusing solely on essential boundaries, avoiding excessive example lists.
7. **Clarity & Evidence**: Keep responses actionable, concise, and structured without fluff or guesswork.

---

## 2. Markdown & Text Formatting

1. **GitHub Flavored Markdown (GFM)**: Use standard GFM tables, task lists (`- [ ]`), alerts, and fenced code blocks.
2. **Alert Callouts**: Use GitHub callouts sparingly and appropriately:
   - `> [!NOTE]` for contextual background.
   - `> [!TIP]` for optimizations and best practices.
   - `> [!IMPORTANT]` for essential operational constraints.
   - `> [!WARNING]` for breaking changes and deprecations.
   - `> [!CAUTION]` for destructive or risky actions.
3. **Code Block Identifiers**: Always specify the language identifier (e.g. `ts`, `bash`, `json`, `mermaid`) when declaring fenced code blocks.
4. **Mandatory Space After Emphasis in Korean**: In Korean text, whenever emphasis (`**bold**` or `*italic*`) is followed by Korean characters/postpositions without whitespace, always insert a space (e.g. `**강조**문구` ❌ ➔ `**강조** 문구` ⭕) to prevent Markdown parser and bold rendering glitches.
   - **Regardless of Internal Content**: Regardless of what symbols reside inside the emphasis tags (inline code backticks, parentheses, hyphens, glob wildcards), **a space is mandatory whenever the closing emphasis mark is followed by a Korean character** (e.g. `**번역본(`*-ko.md`)**을` ❌ ➔ `**번역본(`*-ko.md`)** 을` ⭕).
   - **Verification Pattern**: Validated via `(?<=\S)\*\*(?=[가-힣])` to ensure zero attached Korean particles after closing bold markers.
5. **Tilde (`~`) Strikethrough Prevention**: When writing ranges or intervals, prefer hyphens (e.g. `2023 - 2024`) or strictly escape tildes with backslashes (`\~`, e.g. `2023\~2024`) to prevent Markdown engines from erroneously parsing them as strikethrough markup (`~~strike~~`).

---

## 3. File Links & Code References

1. **Readable Link Text**: Use file basenames (e.g., `protocol.md`, `App.tsx`) as link text rather than full filesystem paths.
2. **Forward Slashes**: Always normalize file paths to forward slashes `/` even on Windows.

---

## 4. Mathematics & LaTeX Formatting

1. **KaTeX Standard**: Mathematical expressions should be rendered using standard KaTeX:
   - Inline math: `$x + y = z$` or `\(x + y = z\)`
   - Block math: `$$E = mc^2$$` or `\[E = mc^2\]`
2. **Literal Dollar Escaping**: Always escape literal currency or shell symbols (`\$` or inside backticks `` `$VAR` ``) to prevent unintended math rendering in markdown parsers.

---

## 5. Bilingual Documentation Synchronization (Sync)

1. **Strict 1:1 Parity**: Every rule and guide file exists in both English and Korean (e.g. `rules/<name>.md` and `rules/<name>-ko.md`, `GEMINI.md` and `GEMINI-ko.md`, `README.md` and `README-en.md`).
2. **Simultaneous Updates**: Whenever a rule, specification, or workflow detail in one language is modified or created, its counterpart file in the other language **must be updated in the same turn/commit** to keep both versions perfectly synchronized. Never leave documentation out-of-sync.
