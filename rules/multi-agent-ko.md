# 멀티 에이전트 실행 규칙 (Multi-Agent Operating Rules)

본 문서는 워크스페이스 내에서 총괄 PM과 전문 서브에이전트들이 준수해야 할 **멀티 에이전트 역할 분담, 파이프라인 시퀀스 및 실행 관문(Gates)** 을 규정합니다.

---

## 1. 기본 원칙

1. **역할 분리와 단독 구현 금지**:
   - 총괄 PM(메인 대화창의 AI)은 요구사항 분석, 아키텍처 수립, 업무 라우팅, 사용자 승인 게이트 관리 및 최종 결과 취합을 전담합니다.
   - 기능 구현 시 총괄 PM이 직접 소스코드를 편집하지 않으며, 반드시 도구(`define_subagent`, `invoke_subagent`)를 통해 전문 서브에이전트를 출격시켜 격리 브랜치(`branch` 모드)에서 구현을 수행합니다.
2. **화면 승인 필수 관문 (User Screen Approval Gate)**:
   - UI가 포함된 기능 구현 시, 프론트엔드 작업 완료 및 화면 검사관(`ui-auditor`)의 스크린샷 아티팩트가 생성되면 **총괄 PM은 즉시 모든 다음 단계를 멈추고 사용자에게 화면 승인을 요청** 합니다.
   - 사용자가 명시적으로 화면을 승인하기 전까지는 백엔드 구현이나 다음 단계로 진입할 수 없습니다.
3. **스키마 계약 기반 인수인계**:
   - 프론트엔드가 정의한 Mock 데이터 및 TypeScript/Zod 인터페이스는 백엔드 구현의 단일 계약(SSOT)이 됩니다. 백엔드는 프론트엔드 필드명을 임의로 변경할 수 없습니다.
4. **TDD 올그린 통과 원칙**:
   - 백엔드 구현 후 `tester` 에이전트가 테스트를 실행하며, 100% 올그린(All Green)을 달성할 때까지 자율 디버깅을 반복합니다.
5. **누적 3회 커밋 감사 (Self-Healing Loop)**:
   - 총괄 PM은 커밋 발생 시 Git 커밋 수를 자체 확인하여, **누적 3회차 커밋 달성 시** 또는 대규모 diff 발생 시 `code-reviewer` 를 호출하여 린트, 스타일 컨벤션, 한글 주석, 보안 수칙을 정밀 감사하고 자율 수정을 유도합니다.

---

## 2. 5대 전문 에이전트 역할 및 권한 명세

| 역할 | 에이전트 식별자 | 작업 공간 | 필수 주입 스킬 파일 (SKILL.md 경로) | 주요 책임 및 행동 규약 |
| :--- | :--- | :--- | :--- | :--- |
| **총괄 PM** | `pm` (메인 AI) | `inherit` | - | 요구사항 분석, 서브에이전트 오케스트레이션(스킬 주입), 사용자 승인 관문 제어, 최종 보고 |
| **프론트엔드** | `frontend-agent` | `branch` (격리) | `.agents/skills/ui-ux-pro-max/SKILL.md`<br>`.agents/skills/seo/SKILL.md` | 순수 모던 CSS(@layer, @container, CSS 변수), Headless UI, 모바일 퍼스트(<640px, 44px 터치 타깃), Mock 데이터 및 Zod 스키마 선언, 시맨틱 마크업 준수 |
| **화면 검사관** | `ui-auditor` | `inherit` | Chrome DevTools MCP | Chrome DevTools MCP 기반 모바일/데스크톱 렌더링 검증, 콘솔 에러 검사, **스크린샷 아티팩트 자동 팝업** |
| **백엔드/API** | `backend-agent` | `branch` (격리) | `.agents/skills/tdd/SKILL.md` | 프론트 스키마 100% 계승, RESTful API 엔드포인트, DB 트랜잭션, 구조화된 로깅, Seam(경계면) 중심의 수직 슬라이스 TDD 구현 |
| **테스트 러너** | `tester` | `branch` (격리) | `.agents/skills/tdd/SKILL.md` | 단위/통합 테스트 자동 실행, 실패 로그 추출 ➔ 개발 에이전트 자율 디버깅 연계 |
| **코드 리뷰어** | `code-reviewer` | `inherit` (읽기 전용) | `.agents/skills/code-review/SKILL.md` | 누적 3회 커밋 시 출격, 2축(Spec 축: PRD 요구사항 충족 / Standards 축: 8대 규칙·코드스멜) 정밀 감사 및 자율 셀프힐링 피드백 |

### 2.1 스킬 강제 주입 규약 (Mandatory Skill Injection Protocol)
> [!IMPORTANT]
> **스킬은 일반 명사가 아닌 물리적 지침 파일입니다.**
> 서브에이전트는 독립된 컨텍스트에서 실행되므로, 총괄 PM이 프롬프트에 명시하지 않으면 스킬을 인식하지 못합니다.
> 따라서 총괄 PM은 서브에이전트 호출(`invoke_subagent`) 시, **`Prompt` 인자의 첫머리에 반드시 아래 지침을 물리적으로 주입** 해야 합니다:
> - **프론트엔드 호출 시**: `Prompt: "[필수 사전 실행: view_file로 .agents/skills/ui-ux-pro-max/SKILL.md 및 .agents/skills/seo/SKILL.md를 먼저 읽고 지침을 100% 준수할 것] ..."`
> - **백엔드/테스터 호출 시**: `Prompt: "[필수 사전 실행: view_file로 .agents/skills/tdd/SKILL.md를 먼저 읽고 수직 슬라이스 및 Seam 기반 TDD 지침을 100% 준수할 것] ..."`
> - **코드 리뷰어 호출 시**: `Prompt: "[필수 사전 실행: view_file로 .agents/skills/code-review/SKILL.md를 먼저 읽고, PRD.md(Spec 축)와 rules/(Standards 축)의 2축 독립 리뷰를 수행할 것] ..."`

---

## 3. 4대 모듈형 파이프라인 시퀀스

작업 요청이 들어오면 총괄 PM은 다음 시퀀스를 기계적으로 준수하여 서브에이전트를 지휘합니다:

```
[사용자 요청 접수]
       │
       ├─► [경로 A: 화면 개발 포함]
       │     └─► 1. frontend-agent (ui-ux-pro-max, seo 참조) + ui-auditor 호출
       │     └─► 2. 스크린샷 아티팩트 팝업
       │     └─► 3. 🛑 개발자 화면 승인 대기 (사용자 승인 시까지 STOP)
       │     └─► 4. backend-agent (tdd 참조) + tester 호출 (TDD 올그린 달성)
       │
       └─► [경로 B: 순수 백엔드/DB/배치 로직]
             └─► 1. 모듈 1 전면 생략 (화면/검사관 호출 안 함)
             └─► 2. backend-agent (tdd 참조) + tester 직행 (TDD 올그린 달성)
       │
[3회 커밋 주기 체크] ──► 누적 3회 시 code-reviewer (code-review 참조) 자동 감사
       │
[최종 3줄 보고 및 사용자 커밋 승인 요청]
```

### 3.1 모듈별 실행 지침
- **모듈 1 (화면 개발 & 검사)**: `frontend-agent`(`ui-ux-pro-max`, `seo`)가 컴포넌트·Mock 스키마 작성 ➔ `ui-auditor`가 스크린샷 아티팩트 팝업 ➔ **🛑 사용자 화면 승인 전까지 일체 중단 (Stop)**.
- **모듈 2 (백엔드 구현)**: `backend-agent`(`tdd`)가 프론트 스키마 계약을 100% 계승하여 Seam 중심 API·DB 구현.
- **모듈 3 (테스트 검증)**: `tester`가 단위/통합 테스트를 실행하고 100% 올그린 통과까지 자율 디버깅.
- **모듈 4 (품질 감사)**: 누적 3회 커밋 시 `code-reviewer`(`code-review`)가 출격하여 Spec(PRD 준수) 및 Standards(8대 규칙) 2축 감사 수행.


---

## 4. 예외 및 단일 에이전트 허용 범위

다음의 경미한 작업에 한해서는 서브에이전트 분할 없이 총괄 PM이 직접 수정할 수 있습니다:
- 단순 오탈자 및 마크다운 문서(`*.md`) 수정
- 1~2줄 이내의 경미한 버그 픽스 또는 스타일 매직 넘버 수정
- 기획 문서(`PRD.md`) 자체의 갱신 작업
