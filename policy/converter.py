"""
Raw HDF5 → LeRobot 포맷 변환기.
수집은 raw HDF5로, 학습 직전에 이 스크립트로 변환.

사용:
    python converter.py --input ~/rllab_datasets/session_xxx/ --output ~/lerobot_datasets/skill_grasp/
"""
import argparse
import os


def convert_session(input_dir: str, output_dir: str):
    """세션 폴더 내 모든 episode HDF5를 LeRobot 포맷으로 변환.
    
    Args:
        input_dir: raw HDF5 파일들이 있는 세션 폴더
        output_dir: LeRobot 포맷 출력 경로
    """
    # TODO:
    # 1. input_dir 내 episode_*.hdf5 목록
    # 2. 각 HDF5 읽기 (observations, actions, timestamps)
    # 3. 이미지 리사이즈 + mp4 인코딩 (LeRobot 요구)
    # 4. joint state 정규화
    # 5. LeRobot 데이터셋 구조로 저장
    # 6. meta/info.json 생성
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="raw HDF5 세션 폴더")
    parser.add_argument("--output", required=True, help="LeRobot 포맷 출력 경로")
    args = parser.parse_args()
    convert_session(args.input, args.output)
