# 1. 베이스 이미지 (Ubuntu 24.04 기반)
FROM vllm/vllm-openai:latest-cu130-ubuntu2404

ENV DEBIAN_FRONTEND=noninteractive \
    HF_HOME=/workspace/model_cache \
    HF_HUB_CACHE=/workspace/model_cache/hub \
    PYTHONPATH=/workspace \
    ROS_DOMAIN_ID=30

# 2. 필수 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ffmpeg libgl1 libglib2.0-0 libgtk2.0-dev pkg-config \
    gcc curl gnupg lsb-release ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. ROS 2 Jazzy repository
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu noble main" \
    > /etc/apt/sources.list.d/ros2.list

# 3. Install ROS 2 Jazzy
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-ros-base \
    ros-jazzy-rclpy \
    ros-jazzy-sensor-msgs \
    ros-jazzy-cv-bridge \
    python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

# 4. ROS environment setup
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc


WORKDIR /workspace

# Keep tools that still use the default root HF cache on the same persistent cache.
RUN mkdir -p /root/.cache && \
    ln -sfn /workspace/model_cache /root/.cache/huggingface

# 5. HPC-X 심볼 에러 방패 (LD_PRELOAD)
RUN echo "void ucs_config_doc_nop(void) {}" > /tmp/dummy_nop.c && \
    gcc -shared -fPIC -o /usr/local/lib/libdummy_nop.so /tmp/dummy_nop.c && \
    rm /tmp/dummy_nop.c
ENV LD_PRELOAD=/usr/local/lib/libdummy_nop.so

# 6. OpenCV 설치 (3.12용으로 설치하여 rclpy와 호환성 유지)
RUN pip uninstall -y opencv-python-headless && \
    pip install --no-cache-dir "opencv-python>=4.10.0"

# 7. 소스 복사 및 진입점 설정
COPY . .
ENTRYPOINT []
CMD ["/bin/bash"]
