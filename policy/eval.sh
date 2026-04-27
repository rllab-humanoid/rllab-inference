#!/bin/bash
# Diffusion Policy 평가 원커맨드
# 사용: bash policy/eval.sh <skill_name> <checkpoint_path>

SKILL=${1:?"\n사용법: bash policy/eval.sh <skill_name> <checkpoint>"}
CKPT=${2:?"checkpoint 경로 필요"}

echo "=== Evaluating: ${SKILL} ==="
echo "Checkpoint: ${CKPT}"

# TODO: 실제 평가 커맨드
echo "TODO: 평가 구현 필요"
