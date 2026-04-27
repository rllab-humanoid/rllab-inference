"""
YOLO 추론 + bbox 오버레이.
실시간 30Hz로 조종자 모니터에 bbox 표시 (A구간 심사 기준).

사용:
    python yolo_infer.py --weights best.pt --source 0
"""
import argparse


def infer(weights: str, source: str = "0"):
    """YOLO 추론 루프. bbox를 화면에 오버레이."""
    # TODO: YOLO 추론 + bbox 오버레이
    raise NotImplementedError


def scene_to_text(detections: list) -> str:
    """YOLO 결과를 Agent에 전달할 텍스트로 변환.
    
    예: [{"label": "flange_nut", "bbox": [234,156,280,200], "conf": 0.95}]
     → "flange_nut(234,156) conf=0.95, hex_nut(400,300) conf=0.91"
    """
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", required=True)
    parser.add_argument("--source", default="0")
    args = parser.parse_args()
    infer(args.weights, args.source)
