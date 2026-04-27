# 브랜치 / 커밋 / PR 컨벤션

## 브랜치
- `main` — 동작 보장 버전 (PR 머지만)
- `dev` — 개발 통합
- `feat/A-docker-setup` — Subteam + 기능명
- `feat/D-robot-cli` — Subteam + 기능명
- `fix/yolo-bbox-offset` — 버그 수정

## 커밋 메시지
```
<type>(<scope>): <설명>

예시:
feat(agent): Robot CLI stub 구현
feat(perception): YOLO 학습 스크립트 추가
fix(policy): converter timestamp 오류 수정
data(collection): skill config 업데이트
docs: WORKFLOW.md 추가
```

type: feat / fix / data / docs / refactor / test

## PR
- `dev` ← feature 브랜치로 PR
- 최소 1명 리뷰 후 머지
- Phase 1에선 빠른 진행 우선, 리뷰 가볍게

## 코드 스타일
- Python: black 포매터
- Type hints 권장 (필수 아님)
- Docstring: 함수마다 최소 한 줄
