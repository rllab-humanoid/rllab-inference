#!/usr/bin/env python3
"""Record joint positions from /joint_states and save them to individual files.

Usage:
    ros2 run physical_ai_inference_client record_joint_positions

로봇을 원하는 자세로 이동시킨 뒤 Enter를 눌러 스냅샷한다.
각 스냅샷은 이름을 부여하면 즉시 파일로 저장된다.
'q' 입력 시 전체 기록 요약을 출력하고 종료한다.
"""

import os
import sys
from datetime import datetime

import rclpy
import yaml
from rclpy.node import Node
from sensor_msgs.msg import JointState


ARM_L_JOINTS = [
    'arm_l_joint1', 'arm_l_joint2', 'arm_l_joint3', 'arm_l_joint4',
    'arm_l_joint5', 'arm_l_joint6', 'arm_l_joint7', 'gripper_l_joint1',
]
ARM_R_JOINTS = [
    'arm_r_joint1', 'arm_r_joint2', 'arm_r_joint3', 'arm_r_joint4',
    'arm_r_joint5', 'arm_r_joint6', 'arm_r_joint7', 'gripper_r_joint1',
]
HEAD_JOINTS = ['head_joint1', 'head_joint2']
LIFT_JOINTS = ['lift_joint']

SAVE_DIR = os.path.join(os.path.expanduser('~'), 'joint_recordings')


class JointPositionRecorder(Node):

    def __init__(self) -> None:
        super().__init__('joint_position_recorder')
        self.declare_parameter('joint_states_topic', '/joint_states')
        topic = str(self.get_parameter('joint_states_topic').value)
        self._latest_msg: JointState | None = None
        self.create_subscription(JointState, topic, self._callback, 10)
        self.get_logger().info(f'Subscribed to {topic}')

    def _callback(self, msg: JointState) -> None:
        self._latest_msg = msg

    def spin_for_fresh_state(self, timeout_sec: float = 5.0) -> JointState | None:
        self._latest_msg = None
        deadline = self.get_clock().now().nanoseconds + int(timeout_sec * 1e9)
        while self._latest_msg is None:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.get_clock().now().nanoseconds > deadline:
                return None
        return self._latest_msg

    def extract_positions(
        self, msg: JointState, joint_names: list[str]
    ) -> list[float] | None:
        name_list = list(msg.name)
        try:
            return [round(msg.position[name_list.index(j)], 6) for j in joint_names]
        except ValueError as exc:
            self.get_logger().warning(f'Joint not found in /joint_states: {exc}')
            return None


def _format_positions_block(step_name: str, positions: dict[str, list[float]]) -> str:
    lines = [f'{step_name}:']
    for key, values in positions.items():
        formatted = '[' + ', '.join(f'{v:.6f}' for v in values) + ']'
        lines.append(f'  {key}: {formatted}')
    return '\n'.join(lines)


def _save_to_file(step_name: str, positions: dict[str, list[float]]) -> str:
    os.makedirs(SAVE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{step_name}_{timestamp}.yaml'
    filepath = os.path.join(SAVE_DIR, filename)
    data = {step_name: {k: v for k, v in positions.items()}}
    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=True, sort_keys=False)
    return filepath


def main(args: list[str] | None = None) -> int:
    rclpy.init(args=args)
    node = JointPositionRecorder()

    snapshots: list[tuple[str, dict, str]] = []  # (name, positions, filepath)

    print('\n=== Joint Position Recorder ===')
    print(f'저장 위치: {SAVE_DIR}')
    print('로봇을 원하는 자세로 이동한 뒤 Enter → 이름 입력 → 즉시 파일 저장.')
    print('"q" 입력 시 전체 요약 출력 후 종료.\n')

    while rclpy.ok():
        try:
            user_input = input('스냅샷: Enter  /  종료: q > ')
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.strip().lower() == 'q':
            break

        msg = node.spin_for_fresh_state(timeout_sec=5.0)
        if msg is None:
            print('  ERROR: /joint_states 타임아웃. 로봇이 실행 중인지 확인하세요.')
            continue

        try:
            step_name = input('  이름 (step name) > ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not step_name:
            print('  이름이 없으면 저장하지 않음.\n')
            continue

        positions: dict[str, list[float]] = {}
        for key, joint_names in [
            ('arm_l_positions', ARM_L_JOINTS),
            ('arm_r_positions', ARM_R_JOINTS),
            ('head_positions', HEAD_JOINTS),
            ('lift_positions', LIFT_JOINTS),
        ]:
            pos = node.extract_positions(msg, joint_names)
            if pos is not None:
                positions[key] = pos
            else:
                print(f'  WARNING: {key} 읽기 실패 — 해당 항목 생략.')

        filepath = _save_to_file(step_name, positions)
        snapshots.append((step_name, positions, filepath))

        print(f'\n  [{len(snapshots)}] "{step_name}" 저장됨 → {filepath}')
        print('  ' + '-' * 50)
        for key, values in positions.items():
            formatted = '[' + ', '.join(f'{v:.6f}' for v in values) + ']'
            print(f'  {key}: {formatted}')
        print()

    # 최종 요약
    if not snapshots:
        print('\n기록된 스냅샷 없음.')
    else:
        print('\n' + '=' * 60)
        print(f'  총 {len(snapshots)}개 기록 요약')
        print('=' * 60)
        for i, (step_name, positions, filepath) in enumerate(snapshots, start=1):
            print(f'\n[{i}] {step_name}  ({os.path.basename(filepath)})')
            for key, values in positions.items():
                formatted = '[' + ', '.join(f'{v:.6f}' for v in values) + ']'
                print(f'  {key}: {formatted}')

        print('\n' + '=' * 60)
        print('# initial_positions.yaml 붙여넣기용 블록')
        print('=' * 60)
        step_name_list = [name for name, _, _ in snapshots]
        print(f'\nstep_names: [{", ".join(step_name_list)}]\n')
        for step_name, positions, _ in snapshots:
            print(_format_positions_block(step_name, positions))
            print()

    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
