# rllab-humanoid

2026 휴머노이드 챌린지 — RLLAB (POSTECH)

## 구조

```
agent/          ← Gemma 4 Agent + Robot CLI
perception/     ← YOLO 학습/추론
policy/         ← Diffusion Policy 학습/평가 + converter
scripts/        ← 환경 세팅, 에피소드 실행
docs/           ← 워크플로우, 컨벤션
```

## 퀵스타트

```bash
# 환경 세팅
bash scripts/setup_docker.sh

# 더미 에피소드 실행
python scripts/run_episode.py --dummy

# YOLO 학습
python perception/yolo_train.py --data perception/data/parts.yaml

# Diffusion Policy 학습
bash policy/train.sh grasp

# Agent 테스트
python agent/gemma_server.py
```

## 관련 레포

- [rllab-data-collection](https://github.com/rllab-postech/rllab-data-collection) — 데이터 수집 전용

## 문서

- [WORKFLOW.md](docs/WORKFLOW.md) — 작업 흐름
- [CONVENTIONS.md](docs/CONVENTIONS.md) — 브랜치/커밋 규칙
- [Notion 워크스페이스](https://www.notion.so/Humanoid-Challenge-34446393d1dc80fbb552cb5332c11f50)
