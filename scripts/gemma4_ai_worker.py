#!/usr/bin/env python3
"""
Gemma 4 AI Worker — ZED 카메라에서 이미지를 받아 Gemma 4로 Task Recognition 수행.

기본적으로 ROS2 이미지 토픽에서 프레임 1장을 직접 받아오고,
tr_agent.py 의 TaskRecognition_VLM_Agent 로 부품 인식을 수행한다.
원하면 이미지 없이 텍스트만 보낼 수도 있고, 로컬 이미지 파일 1장을 직접 넘기거나,
기존 HTTP snapshot 서버를 통해서도 이미지를 받을 수 있다.

사용:
    python scripts/gemma4_ai_worker.py --zone A
    python scripts/gemma4_ai_worker.py --zone A --compressed-topic /zed/zed_node/rgb/image_rect_color/compressed
    python scripts/gemma4_ai_worker.py --zone A --image-topic /camera/color/image_raw
    python scripts/gemma4_ai_worker.py --zone A --image-path /tmp/test.jpg
    python scripts/gemma4_ai_worker.py --zone A --loop --interval 2.0
    python scripts/gemma4_ai_worker.py --zone A --save-dir /tmp/snapshots
"""

import argparse
import os
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

import requests
from PIL import Image as PILImage

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agent.tr_agent import TaskRecognition_VLM_Agent

DEFAULT_STREAM_HOST = "localhost"
DEFAULT_STREAM_PORT = 8080
SNAPSHOT_ENDPOINT = "/snapshot.jpg"
DEFAULT_COMPRESSED_TOPIC = "/zed/zed_node/rgb/image_rect_color/compressed"
DEFAULT_IMAGE_TOPIC = None
DEFAULT_TR_BACKEND = os.getenv("TR_AGENT_BACKEND", "server").lower()
DEFAULT_VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:30000/v1")
DEFAULT_TEXT_PROMPT = None


def is_vllm_healthy(base_url: str, timeout: float = 3.0) -> bool:
    health_url = base_url.rstrip("/").removesuffix("/v1") + "/health"
    try:
        response = requests.get(health_url, timeout=timeout)
        return response.ok
    except requests.RequestException:
        return False


def fetch_snapshot(host: str, port: int, timeout: float = 5.0) -> bytes:
    """ZED HTTP 서버(/snapshot.jpg)에서 JPEG 이미지를 가져온다."""
    url = f"http://{host}:{port}{SNAPSHOT_ENDPOINT}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"ZED 스트림 서버({url})에 연결할 수 없습니다. "
            "stream_zed.py 가 실행 중인지 확인하세요."
        ) from exc


def capture_compressed_ros_image(topic: str, timeout_sec: float = 8.0) -> bytes:
    """ROS2 CompressedImage 토픽에서 JPEG 바이트 1프레임을 받는다."""
    try:
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import CompressedImage
    except ImportError as exc:
        raise RuntimeError(
            "ROS2 Python(rclpy, sensor_msgs) 환경이 필요합니다. "
            "ROS2 setup 후 다시 실행하세요."
        ) from exc

    frame = {"data": None}

    def _callback(msg: "CompressedImage") -> None:
        frame["data"] = bytes(msg.data)

    rclpy.init()
    node = rclpy.create_node("gemma4_worker_compressed_grabber")
    _sub = node.create_subscription(
        CompressedImage,
        topic,
        _callback,
        qos_profile_sensor_data,
    )

    start = time.time()
    try:
        while frame["data"] is None and (time.time() - start) < timeout_sec:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    if frame["data"] is None:
        raise TimeoutError(f"{timeout_sec}s 내에 {topic} 에서 CompressedImage 프레임을 받지 못했습니다.")

    return frame["data"]


def capture_raw_ros_image(topic: str, timeout_sec: float = 8.0) -> bytes:
    """ROS2 raw Image 토픽에서 JPEG 바이트 1프레임을 만든다."""
    try:
        import io
        import rclpy
        from sensor_msgs.msg import Image
    except ImportError as exc:
        raise RuntimeError(
            "ROS2 Python(rclpy, sensor_msgs) 환경이 필요합니다. "
            "ROS2 setup 후 다시 실행하세요."
        ) from exc

    frame = {"data": None, "error": None}

    def _callback(msg: "Image") -> None:
        try:
            if msg.encoding == "rgb8":
                image = PILImage.frombytes("RGB", (msg.width, msg.height), bytes(msg.data))
            elif msg.encoding == "bgr8":
                image = PILImage.frombytes("RGB", (msg.width, msg.height), bytes(msg.data), "raw", "BGR")
            elif msg.encoding == "mono8":
                image = PILImage.frombytes("L", (msg.width, msg.height), bytes(msg.data))
            else:
                frame["error"] = f"지원하지 않는 인코딩: {msg.encoding}"
                return

            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            frame["data"] = buffer.getvalue()
        except Exception as exc:  # pragma: no cover - runtime callback safety
            frame["error"] = str(exc)

    rclpy.init()
    node = rclpy.create_node("gemma4_worker_image_grabber")
    _sub = node.create_subscription(Image, topic, _callback, 10)

    start = time.time()
    try:
        while frame["data"] is None and (time.time() - start) < timeout_sec:
            rclpy.spin_once(node, timeout_sec=0.2)
            if frame["error"]:
                raise RuntimeError(f"ROS2 이미지 수신 실패: {frame['error']}")
    finally:
        node.destroy_node()
        rclpy.shutdown()

    if frame["data"] is None:
        raise TimeoutError(f"{timeout_sec}s 내에 {topic} 에서 raw Image 프레임을 받지 못했습니다.")

    return frame["data"]


def get_snapshot_bytes(
    compressed_topic: str | None = DEFAULT_COMPRESSED_TOPIC,
    image_topic: str | None = DEFAULT_IMAGE_TOPIC,
    stream_host: str | None = None,
    stream_port: int = DEFAULT_STREAM_PORT,
) -> bytes:
    """우선순위에 따라 ROS compressed, ROS raw, HTTP snapshot 중 하나로 이미지를 얻는다."""
    if compressed_topic:
        return capture_compressed_ros_image(compressed_topic)
    if image_topic:
        return capture_raw_ros_image(image_topic)
    if stream_host:
        return fetch_snapshot(stream_host, stream_port)
    raise RuntimeError(
        "이미지를 가져올 입력이 없습니다. "
        "--compressed-topic, --image-topic, 또는 --stream-host 중 하나를 지정하세요."
    )


def run_worker(
    zone: str,
    compressed_topic: str | None = DEFAULT_COMPRESSED_TOPIC,
    image_topic: str | None = DEFAULT_IMAGE_TOPIC,
    image_path: str | None = None,
    stream_host: str | None = None,
    stream_port: int = DEFAULT_STREAM_PORT,
    backend: str = DEFAULT_TR_BACKEND,
    vllm_base_url: str | None = None,
    use_robot_image: bool = True,
    text_prompt: str | None = DEFAULT_TEXT_PROMPT,
    loop: bool = False,
    interval: float = 2.0,
    save_dir: str | None = None,
) -> dict | None:
    """Gemma 4 Task Recognition 워커를 실행한다.

    Args:
        zone: 작업 구역 ("A" 또는 "C")
        compressed_topic: ROS2 CompressedImage 토픽
        image_topic: ROS2 raw Image 토픽
        image_path: 모델에 직접 전달할 단일 이미지 파일 경로
        stream_host: ZED 스트림 서버 호스트
        stream_port: ZED 스트림 서버 포트
        backend: `local` 또는 `server`
        vllm_base_url: vLLM OpenAI-compatible API base URL
        use_robot_image: True 이면 로봇/카메라 이미지를 함께 전달
        text_prompt: 기본 zone 프롬프트 대신 사용할 사용자 텍스트
        loop: True 이면 interval 간격으로 반복 실행
        interval: 반복 간격 (초)
        save_dir: 스냅샷 저장 디렉토리. None 이면 임시 파일 사용

    Returns:
        loop=False 일 때 인식 결과 dict 반환. loop=True 이면 None.
    """
    print(
        f"[Gemma4Worker] Zone={zone}, "
        f"backend={backend}, use_robot_image={use_robot_image}, "
        f"image_path={image_path}, compressed_topic={compressed_topic}, image_topic={image_topic}, "
        f"stream={stream_host}:{stream_port}" if stream_host else
        f"[Gemma4Worker] Zone={zone}, backend={backend}, use_robot_image={use_robot_image}, "
        f"image_path={image_path}, compressed_topic={compressed_topic}, image_topic={image_topic}"
    )
    resolved_vllm_base_url = vllm_base_url or os.getenv("VLLM_BASE_URL") or DEFAULT_VLLM_BASE_URL
    if backend == "server" and not is_vllm_healthy(resolved_vllm_base_url):
        raise RuntimeError(
            "vLLM 서버가 준비되어 있지 않습니다. "
            f"`{resolved_vllm_base_url}` 를 확인하고 다른 터미널에서 먼저 서버를 실행하세요."
        )
    agent = TaskRecognition_VLM_Agent(
        zone,
        backend=backend,
        vllm_base_url=resolved_vllm_base_url,
    )

    save_path = Path(save_dir) if save_dir else None
    if save_path:
        save_path.mkdir(parents=True, exist_ok=True)

    def _run_once() -> dict:
        img_path = None
        if image_path:
            resolved_image_path = Path(image_path).expanduser().resolve()
            if not resolved_image_path.is_file():
                raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {resolved_image_path}")
            img_path = str(resolved_image_path)
        elif use_robot_image:
            jpeg_bytes = get_snapshot_bytes(
                compressed_topic=compressed_topic,
                image_topic=image_topic,
                stream_host=stream_host,
                stream_port=stream_port,
            )

            if save_path:
                img_file = save_path / f"frame_{int(time.time() * 1000)}.jpg"
                img_file.write_bytes(jpeg_bytes)
                img_path = str(img_file)
            else:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(jpeg_bytes)
                    img_path = tmp.name

        return agent.main(img_path=img_path, prompt_text=text_prompt)

    try:
        if loop:
            while True:
                try:
                    result = _run_once()
                    print(f"[{time.strftime('%H:%M:%S')}] 인식 결과: {result}")
                except RuntimeError as exc:
                    print(f"[ERROR] {exc}", file=sys.stderr)
                time.sleep(interval)
            return None

        result = _run_once()
        print("Task Recognition 결과:", result)
        return result
    except KeyboardInterrupt:
        print("\n[Gemma4Worker] 종료.")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemma 4 AI Worker")
    parser.add_argument(
        "--zone", choices=["A", "C"], required=True,
        help="작업 구역 (A 또는 C)",
    )
    parser.add_argument(
        "--compressed-topic", default=DEFAULT_COMPRESSED_TOPIC,
        help=f"ROS2 CompressedImage 토픽 (기본: {DEFAULT_COMPRESSED_TOPIC})",
    )
    parser.add_argument(
        "--image-topic", default=DEFAULT_IMAGE_TOPIC,
        help="ROS2 raw Image 토픽 (예: /camera/color/image_raw)",
    )
    parser.add_argument(
        "--image-path",
        help="모델에 직접 전달할 단일 이미지 파일 경로",
    )
    parser.add_argument(
        "--stream-host", default=None,
        help="기존 HTTP snapshot 서버 호스트 (사용하지 않으면 생략)",
    )
    parser.add_argument(
        "--stream-port", type=int, default=DEFAULT_STREAM_PORT,
        help=f"ZED 스트림 서버 포트 (기본: {DEFAULT_STREAM_PORT})",
    )
    parser.add_argument(
        "--vllm-base-url",
        help="vLLM OpenAI-compatible API 주소 (예: http://127.0.0.1:30000/v1)",
    )
    parser.add_argument(
        "--backend",
        choices=["local", "server"],
        default=DEFAULT_TR_BACKEND,
        help=f"추론 백엔드 선택 (기본: {DEFAULT_TR_BACKEND})",
    )
    parser.add_argument(
        "--no-robot-image", action="store_true",
        help="로봇 이미지를 붙이지 않고 텍스트만 보냄",
    )
    parser.add_argument(
        "--text",
        help="zone 기본 프롬프트 대신 사용할 사용자 텍스트",
    )
    parser.add_argument(
        "--text-file",
        help="보낼 텍스트가 들어있는 파일 경로",
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="반복 실행 모드 (--interval 참고)",
    )
    parser.add_argument(
        "--interval", type=float, default=2.0,
        help="반복 간격 초 (--loop 와 함께 사용, 기본: 2.0)",
    )
    parser.add_argument(
        "--save-dir",
        help="스냅샷 저장 디렉토리 (기본: 임시 파일, 삭제됨)",
    )
    args = parser.parse_args()

    prompt_text = args.text
    if args.text_file:
        prompt_text = Path(args.text_file).read_text(encoding="utf-8")

    run_worker(
        zone=args.zone,
        compressed_topic=args.compressed_topic,
        image_topic=args.image_topic,
        image_path=args.image_path,
        stream_host=args.stream_host,
        stream_port=args.stream_port,
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        use_robot_image=not args.no_robot_image,
        text_prompt=prompt_text,
        loop=args.loop,
        interval=args.interval,
        save_dir=args.save_dir,
    )
