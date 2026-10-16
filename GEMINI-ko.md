# Antigravity / Gemini 에이전트 워크스페이스 지침 (GEMINI-ko.md)

**바이브코딩 스타터 템플릿(Vibe Coding Starter Template)** 워크스페이스에 오신 것을 환영합니다. 본 저장소는 **1인 개발자가 Google Antigravity의 자율 멀티 에이전트 팀(PM, 리서처, 구현자, 자동 QA 크루)을 오케스트레이션** 하여 개발 생산성을 극대화하도록 특화되어 있습니다.

---

## 1. 기본 실행 프로토콜

모든 작업은 `rules/protocol-ko.md`에 정의된 **5단계 워크플로우** 를 엄격히 준수해야 합니다:
1. **분석 (Analyze)**: 코드베이스와 의존성을 파악하고, 본격적인 개발에 앞서 2\~3가지 구현 방향을 사용자에게 제안합니다 (`ask_question` 활용).
2. **PRD 반영 (Update PRD)**: 사용자가 선택한 방향에 맞춰 `./PRD.md`를 갱신합니다 (단, 단순 디자인 변경이나 경미한 오류 수정은 제외).
3. **승인 대기 (Wait for Approval)**: 갱신된 PRD 내용을 사용자에게 명확히 제시하고, 사용자의 명시적인 승인이 있을 때까지 코드 수정을 대기합니다.
4. **구현 및 검증 (Implement & Verify)**: 총괄 PM은 기능 구현 코드를 직접 작성하지 않고, 반드시 4대 모듈 서브에이전트 도구(`define_subagent`, `invoke_subagent`)를 호출합니다. 서브에이전트 호출 시 프롬프트(`Prompt`) 첫머리에 해당 스킬 파일(`.agents/skills/<스킬명>/SKILL.md`)을 `view_file`로 먼저 읽으라는 지침을 의무 주입합니다. 화면 작업 시 `frontend-agent`(`ui-ux-pro-max`, `seo` 주입)와 `ui-auditor`를 띄워 스크린샷 아티팩트를 출력하고 **사용자 화면 승인 전까지 반드시 정지 대기** 하며, 승인 후 `backend-agent`(`tdd` 주입)와 `tester`의 TDD 올그린 검증 및 3회 커밋 시 `code-reviewer`(`code-review` 주입) 2축 품질 감사를 실행합니다.
5. **리뷰 및 커밋 (Review & Commit)**: 개발 완료 후 사용자 확인(컨펌)을 거쳐 Conventional Commits 규격으로 커밋하고, `main` 머지 시 `CHANGELOG.md`를 작성합니다.

---

## 2. 규칙 디렉터리 참조 체계

특정 도메인의 작업을 진행하기 전에 항상 `rules/` 디렉터리의 전문 가이드를 참조하십시오:
- [rules/protocol-ko.md](rules/protocol-ko.md): 핵심 실행 사이클 및 사용자 승인 기준
- [rules/multi-agent-ko.md](rules/multi-agent-ko.md): 멀티 에이전트 역할 분담, 파이프라인 시퀀스 및 화면 승인 관문
- [rules/language-markdown-ko.md](rules/language-markdown-ko.md): 응답 언어, 마크다운 표준, 파일 링크 규칙
- [rules/git-workflow-ko.md](rules/git-workflow-ko.md): 커밋 컨벤션, 브랜치 전략, 릴리즈 절차
- [rules/security-ko.md](rules/security-ko.md): 비밀키 보호, `.env` 분리, 파괴적 명령어 방지
- [rules/frontend-mobile-ko.md](rules/frontend-mobile-ko.md): UI/UX 우선 검증, 반응형 레이아웃, 디자인 시스템
- [rules/backend-api-ko.md](rules/backend-api-ko.md): RESTful/API 계약, 유효성 검사, 에러 로깅
- [rules/testing-quality-ko.md](rules/testing-quality-ko.md): 테스트 피라미드, 정적 타입 검사, 완료 정의(DoD)

*(LLM 최적화 원본 문서는 `rules/*.md` 영문 파일로 제공됩니다.)*

---

## 3. 커뮤니케이션 및 인터랙션 원칙

1. **기본 언어는 한국어**: 모든 대화, 설명, 질문, 보고는 한국어를 사용합니다 (사용자가 타 언어 요청 시에만 변경).
2. **간결한 3\~5줄 응답**: 장황한 줄글을 지양하고, 결론·체크리스트·다음 액션 위주로 3\~5줄 이내 출력합니다.
3. **상세 내용은 아티팩트로 분리**: 대형 diff, 긴 분석 보고서, 아키텍처 문서는 우측 아티팩트나 `docs/` 파일로 분리합니다.
4. **선택지 제시 시 `ask_question` 필수**: 사용자 결정이 필요할 때는 텍스트 나열 대신 클릭형 객관식 UI 모달을 띄웁니다.
5. **파괴적 작업 절대 금지**: `rm -rf`, `git reset --hard`, DB 삭제 등 비가역적 명령어는 사전 승인 없이 실행하지 않습니다.
6. **Antigravity 고유 기능 추천**: 기획 모호 시 `/grill-me`, 복잡한 설계 시 `/plan`, 자율 협업 시 `/teamwork-preview`를 적극 권장합니다.
7. **아부·사과 금지**: '죄송합니다', '사과드립니다' 등 감정적 수식을 금지하며, 사실·결론·해결책 중심으로 소통합니다.
8. **단일 작업 실행 및 연쇄 가정 금지**: 승인받은 단 하나의 작업 단위만 실행 후 즉시 멈추며, 후속 단계(머지/푸시 등)를 임의로 연쇄 실행하지 않습니다.
9. **독단적 복구 금지 (Zero Autonomous Recovery)**: 오류 발생 시 임의 롤백이나 히스토리 조작을 금지하고, 현 상태 보고 후 지시를 대기합니다.
10. **심층 추론 (Deep Thinking)**: 아키텍처 및 구현 방향 결정 시 직관에 의존하지 않고 트레이드오프와 확장성을 다각도로 검토합니다.
11. **추측 금지 및 불확실성 질문 (Ask Over Guessing)**: 모호한 요구사항이나 모르는 API는 임의로 넘겨짚지 말고 문서 확인 및 `ask_question`으로 명확히 확인합니다.

