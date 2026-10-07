# Git Workflow & Release Standards

This document establishes the Git conventions, branching strategy, and release protocols for this repository.

## 1. Commit Message Convention

All commits must follow the Korean Conventional Commits format:

```
<타입>(<스코프>): <간결한 한글 요약>

[상세 한글 본문 (선택)]

[바닥글 (선택)]
```

### Commit Types (한글 커밋 타입)
| Type (타입) | English Equivalent | Purpose (목적) | Example (예시) |
| :--- | :--- | :--- | :--- |
| `기능` | `feat` | 새로운 기능 추가 | `기능(인증): 구글 OAuth2 로그인 연동` |
| `수정` | `fix` | 버그 및 오류 수정 | `수정(장바구니): 음수 수량 입력 방지` |
| `문서` | `docs` | 문서 작성 및 수정 | `문서(prd): 결제 데이터 스키마 명세 업데이트` |
| `개선` | `refactor` | 기능 변경 없는 코드 구조 개선 | `개선(db): 커넥션 풀 싱글톤 패턴 분리` |
| `성능` | `perf` | 성능 향상 및 최적화 | `성능(검색): 자동완성 쿼리 결과 캐싱` |
| `테스트` | `test` | 테스트 코드 추가/수정 | `테스트(api): 주문 결제 통합 테스트 추가` |
| `관리` | `chore` | 빌드, 도구, 의존성 업데이트 | `관리(의존성): biome v1.9 버전 상향` |
| `스타일` | `style` | 코드 포맷팅, 스타일 수정 | `스타일(공통): 린터 포맷팅 규칙 적용` |

### Commit Rules (커밋 작성 규칙)
- All commit types, scopes, summaries, and bodies must be written in Korean.
- Do not end the summary line with a period.
- Ensure commits are atomic: one logical change per commit.
- Keep commit summaries concise and descriptive.

---

## 2. Branching Strategy (Minimal 2-Branch Model)

```
main (Production/Release - Always stable)
 ▲
 │ merge when verified
dev  (Daily development - Antigravity workspace)
```

1. **`main`**: Production branch (verified code and release tags only).
2. **`dev`**: Daily active workspace (feature implementation, bug fixes, refactoring).
3. **`try/<experiment>` (Optional)**: Ephemeral branch for experimental spikes or prototypes.

---

## 3. Merge & Verification Workflow

**Commit, Merge, and Push are strictly independent sequential stages**:

1. **Stage 1: `dev` Commit (Halt immediately upon completion)**:
   - Commit atomic units on `dev` branch with Korean commit format; stop immediately.
2. **Stage 2: `main` Merge (On user instruction)**:
   - Verify tests, linters, PRD, and CHANGELOG before merging:
     ```bash
     git checkout main
     git merge dev --no-ff
     ```
3. **Stage 3: Remote Push (On user instruction)**:
   - Push to `origin` ONLY when explicitly authorized by the user.

---

## 4. Releases & Semantic Versioning (SemVer) Strategy

Adhere to **Semantic Versioning (SemVer)** `vMAJOR.MINOR.PATCH` (`vX.Y.Z`). Tag creation is intentionally decoupled from routine merges:

| Scope | Changes Included | Merge to `main` | Create Git Tag |
| :--- | :--- | :---: | :---: |
| **Z (Patch)** | Typos, docs, styling, small bug fixes, minor refactoring | **Yes** | ❌ **No Tag** (keep merges rapid & lightweight) |
| **Y (Minor)** | Completed PRD feature sets, major module additions | **Yes** | 🏷️ **Create Tag** (`vX.Y.0`) |
| **X (Major)** | Complete architectural overhaul, breaking changes | **Yes** | 🏷️ **Create Tag** (`vX.0.0`) |

### Tagging Rules
1. **Merge Frequency**: Merging stable changes from `dev` to `main` occurs continuously without requiring a tag.
2. **Tag Creation**: Git release tags are reserved exclusively for **Y (Feature completion)** or **X (Major redesign)** milestones. Routine patches and doc maintenance do not create tags.
3. **User Confirmation**: Always confirm with the user before publishing version tags.
