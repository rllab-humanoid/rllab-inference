"""
YOLO v26 학습 스크립트.
Subteam C에서 라벨링한 데이터로 부품 5종 탐지 모델 학습.

사용:
    python yolo_train.py --data perception/data/parts.yaml --epochs 100
"""
import argparse


def train(data_yaml: str, epochs: int = 100, imgsz: int = 640):
    # TODO: ultralytics YOLO 학습
    # from ultralytics import YOLO
    # model = YOLO("yolo11n.pt")
    # model.train(data=data_yaml, epochs=epochs, imgsz=imgsz)
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="perception/data/parts.yaml")
    parser.add_argument("--epochs", type=int, default=100)
    args = parser.parse_args()
    train(args.data, args.epochs)
