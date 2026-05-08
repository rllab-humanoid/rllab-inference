#!/bin/bash
# rllab-humanoid Docker 환경 세팅
# DGX Spark (aarch64 + Blackwell GPU) 기준
set -e

IMAGE_NAME="rllab-humanoid-ros"
CONTAINER_NAME="rllab-humanoid-ros-dev"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

DOCKER_CMD="docker"

resolve_docker_cmd() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "ERROR: docker command not found."
        echo "Install Docker first: https://docs.docker.com/engine/install/"
        exit 1
    fi

    if docker info >/dev/null 2>&1; then
        DOCKER_CMD="docker"
        return
    fi

    if sudo -n docker info >/dev/null 2>&1; then
        DOCKER_CMD="sudo docker"
        echo "[info] Using sudo for Docker daemon access."
        return
    fi

    echo "ERROR: cannot access Docker daemon (permission denied)."
    echo ""
    echo "Fix options:"
    echo "1) Temporary: run this script with sudo"
    echo "   sudo bash scripts/setup_docker.sh"
    echo ""
    echo "2) Permanent (recommended): add your user to docker group"
    echo "   sudo usermod -aG docker $USER"
    echo "   newgrp docker"
    echo "   # then re-run: bash scripts/setup_docker.sh"
    exit 1
}

# 모델 캐시 디렉토리 (컨테이너 재시작 후에도 유지)
MODEL_CACHE="${HOME}/.cache/huggingface"
CONTAINER_MODEL_CACHE="/workspace/model_cache"
mkdir -p "$MODEL_CACHE"

echo "=== rllab-humanoid Docker Setup ==="
echo "Repo : $REPO_ROOT"
echo "Cache: $MODEL_CACHE"
echo ""

resolve_docker_cmd

# ── 1. 이미지 빌드 ────────────────────────────────────────────────────────
echo "[1/2] Building Docker image: $IMAGE_NAME ..."

$DOCKER_CMD build \
    -t "$IMAGE_NAME" \
    -f "$REPO_ROOT/docker/Dockerfile" \
    "$REPO_ROOT"

# ── 2. GUI 권한 허용 (추가된 부분) ───────────────────────────────────────
# 도커 컨테이너(root)가 호스트(DGX)의 X11 디스플레이 서버에 접근할 수 있도록 허용합니다.
echo "Setting up X11 display access..."
xhost +local:root > /dev/null 2>&1 || true

# ── 3. 컨테이너 실행 ─────────────────────────────────────────────────────
echo "[2/2] Starting container: $CONTAINER_NAME ..."

if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[info] Removing existing container: $CONTAINER_NAME"
    $DOCKER_CMD rm -f "$CONTAINER_NAME"
fi

# NVIDIA Spark & Gemma 4 최적화 옵션 적용
$DOCKER_CMD run -it --rm \
    --name "$CONTAINER_NAME" \
    --runtime=nvidia \
    --gpus all \
    --network host \
    --ipc=host \
    --shm-size=32g \
    --privileged \
    -e DISPLAY=$DISPLAY \
    -e QT_X11_NO_MITSHM=1 \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -e HF_HOME="$CONTAINER_MODEL_CACHE" \
    -e HF_HUB_CACHE="$CONTAINER_MODEL_CACHE/hub" \
    ${HF_TOKEN:+-e HF_TOKEN=$HF_TOKEN} \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "$REPO_ROOT":/workspace \
    -v "$MODEL_CACHE":"$CONTAINER_MODEL_CACHE" \
    "$IMAGE_NAME"
    
