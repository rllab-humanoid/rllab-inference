#!/bin/bash
# Diffusion Policy 학습 원커맨드
# 사용: bash policy/train.sh <skill_name>
# 예시: bash policy/train.sh grasp

SKILL=${1:?"\n사용법: bash policy/train.sh <skill_name>"}
CONFIG="policy/configs/${SKILL}.yaml"

if [ ! -f "$CONFIG" ]; then
    echo "Config not found: $CONFIG"
    echo "사용 가능한 skill:"
    ls policy/configs/ | sed 's/.yaml//'
    exit 1
fi

echo "=== Training: ${SKILL} ==="
echo "Config: ${CONFIG}"

# TODO: 실제 학습 커맨드 (LeRobot or 자체 구현)
# python lerobot/scripts/train.py --config $CONFIG
echo "TODO: 학습 구현 필요"
