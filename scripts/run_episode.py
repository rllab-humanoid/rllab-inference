"""
전체 에피소드 실행 스크립트.
Agent (Gemma 4) → Robot CLI → Skill Policy 전체 파이프라인.

사용:
    python scripts/run_episode.py --zone A --image-path /path/to/image.jpg
    python scripts/run_episode.py --zone A --ros-topic /camera/color/image_raw
    python scripts/run_episode.py --zone A --dummy --image-path /path/to/image.jpg
"""
import argparse
import sys
import time
from pathlib import Path

from PIL import Image as PILImage

# Ensure repo-root imports work when launched as: python scripts/run_episode.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.robot_cli import RobotCLI
from scripts.agent.tr_agent import TaskRecognition_VLM_Agent


def capture_single_ros_image(topic: str, output_path: str, timeout_sec: float = 8.0) -> str:
    """ROS2 topic에서 이미지 1프레임을 받아 파일로 저장한다.

    Supports encodings: rgb8, bgr8, mono8.
    """
    try:
        import rclpy
        from sensor_msgs.msg import Image
    except ImportError as exc:
        raise RuntimeError(
            "ROS2 Python(rclpy, sensor_msgs) 환경이 필요합니다. "
            "ROS2 setup 후 다시 실행하세요."
        ) from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    frame = {"saved": False, "error": None}

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

            image.save(output)
            frame["saved"] = True
        except Exception as err:  # pragma: no cover - runtime ROS callback safety
            frame["error"] = str(err)

    rclpy.init()
    node = rclpy.create_node("rllab_episode_image_grabber")
    _sub = node.create_subscription(Image, topic, _callback, 10)

    start = time.time()
    try:
        while not frame["saved"] and (time.time() - start) < timeout_sec:
            rclpy.spin_once(node, timeout_sec=0.2)
            if frame["error"]:
                raise RuntimeError(f"ROS2 이미지 수신 실패: {frame['error']}")
    finally:
        node.destroy_node()
        rclpy.shutdown()

    if not frame["saved"]:
        raise TimeoutError(f"{timeout_sec}s 내에 {topic} 에서 프레임을 받지 못했습니다.")

    return str(output)


def run_episode(
    zone: str,
    dummy: bool = False,
    image_path: str | None = None,
    ros_topic: str | None = None,
):
    cli = RobotCLI()

    if zone != "D":
        tr_agent = TaskRecognition_VLM_Agent(zone)
        final_image_path = image_path

        if final_image_path is None and ros_topic is not None:
            final_image_path = capture_single_ros_image(
                topic=ros_topic,
                output_path="/tmp/rllab_monitor_frame.jpg",
            )

        if final_image_path is None:
            raise ValueError("--image-path 또는 --ros-topic 중 하나는 반드시 지정해야 합니다.")

        output = tr_agent.main(final_image_path)
        print("Task Recognition 결과:", output)
        print("Okay. I'm ready!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", choices=["A", "C", "D"], required=True)
    parser.add_argument("--dummy", action="store_true", help="더미 환경 (로봇 없이)")
    parser.add_argument("--image-path", help="로컬 이미지 파일 경로")
    parser.add_argument("--ros-topic", help="ROS2 이미지 토픽 (예: /camera/color/image_raw)")
    args = parser.parse_args()
    run_episode(args.zone, args.dummy, args.image_path, args.ros_topic)
