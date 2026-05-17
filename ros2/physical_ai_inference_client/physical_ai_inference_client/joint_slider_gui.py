#!/usr/bin/env python3
"""Tk slider GUI for sending joint targets through FollowJointTrajectory actions."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

import rclpy
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


@dataclass(frozen=True)
class ControllerSpec:
    name: str
    action_name: str
    joint_names: tuple[str, ...]


DEFAULT_CONTROLLERS = (
    ControllerSpec(
        name='arm_l',
        action_name='/arm_l_controller/follow_joint_trajectory',
        joint_names=(
            'arm_l_joint1', 'arm_l_joint2', 'arm_l_joint3', 'arm_l_joint4',
            'arm_l_joint5', 'arm_l_joint6', 'arm_l_joint7', 'gripper_l_joint1',
        ),
    ),
    ControllerSpec(
        name='arm_r',
        action_name='/arm_r_controller/follow_joint_trajectory',
        joint_names=(
            'arm_r_joint1', 'arm_r_joint2', 'arm_r_joint3', 'arm_r_joint4',
            'arm_r_joint5', 'arm_r_joint6', 'arm_r_joint7', 'gripper_r_joint1',
        ),
    ),
    ControllerSpec(
        name='head',
        action_name='/head_controller/follow_joint_trajectory',
        joint_names=('head_joint1', 'head_joint2'),
    ),
    ControllerSpec(
        name='lift',
        action_name='/lift_controller/follow_joint_trajectory',
        joint_names=('lift_joint',),
    ),
)


class JointSliderNode(Node):
    def __init__(self) -> None:
        super().__init__('joint_slider_gui')
        self.declare_parameter('joint_states_topic', '/joint_states')
        self.declare_parameter('min_position', -1.5)
        self.declare_parameter('max_position', 1.5)
        self.declare_parameter('trajectory_duration_s', 1.0)
        self.declare_parameter('server_wait_timeout_s', 0.2)
        self.declare_parameter('arm_l_action', DEFAULT_CONTROLLERS[0].action_name)
        self.declare_parameter('arm_r_action', DEFAULT_CONTROLLERS[1].action_name)
        self.declare_parameter('head_action', DEFAULT_CONTROLLERS[2].action_name)
        self.declare_parameter('lift_action', DEFAULT_CONTROLLERS[3].action_name)

        action_overrides = {
            'arm_l': str(self.get_parameter('arm_l_action').value),
            'arm_r': str(self.get_parameter('arm_r_action').value),
            'head': str(self.get_parameter('head_action').value),
            'lift': str(self.get_parameter('lift_action').value),
        }
        self.controllers = tuple(
            ControllerSpec(spec.name, action_overrides[spec.name], spec.joint_names)
            for spec in DEFAULT_CONTROLLERS
        )

        self._lock = threading.Lock()
        self._latest_joint_state: JointState | None = None
        joint_states_topic = str(self.get_parameter('joint_states_topic').value)
        self.create_subscription(JointState, joint_states_topic, self._joint_state_callback, 10)
        self.get_logger().info(f'Subscribed to {joint_states_topic}')

        self.action_clients = {
            spec.name: ActionClient(self, FollowJointTrajectory, spec.action_name)
            for spec in self.controllers
        }
        for spec in self.controllers:
            self.get_logger().info(
                f'{spec.name}: FollowJointTrajectory action -> {spec.action_name}'
            )

    @property
    def min_position(self) -> float:
        return float(self.get_parameter('min_position').value)

    @property
    def max_position(self) -> float:
        return float(self.get_parameter('max_position').value)

    @property
    def duration_s(self) -> float:
        return float(self.get_parameter('trajectory_duration_s').value)

    def _joint_state_callback(self, msg: JointState) -> None:
        with self._lock:
            self._latest_joint_state = msg

    def latest_positions(self) -> dict[str, float]:
        with self._lock:
            msg = self._latest_joint_state
        if msg is None:
            return {}
        return {name: float(position) for name, position in zip(msg.name, msg.position)}

    def send_controller(self, spec: ControllerSpec, positions: list[float]) -> str:
        client = self.action_clients[spec.name]
        wait_timeout = float(self.get_parameter('server_wait_timeout_s').value)
        if not client.wait_for_server(timeout_sec=wait_timeout):
            return f'{spec.name}: action server unavailable ({spec.action_name})'

        current_positions = self.latest_positions()
        target_pairs = list(zip(spec.joint_names, positions))
        target_text = ', '.join(f'{name}={value:.3f}' for name, value in target_pairs)
        self.get_logger().info(f'{spec.name}: target [{target_text}]')

        if current_positions:
            observed_pairs = [
                (name, current_positions[name])
                for name in spec.joint_names
                if name in current_positions
            ]
            if observed_pairs:
                observed_text = ', '.join(
                    f'{name}={value:.3f}' for name, value in observed_pairs
                )
                self.get_logger().info(f'{spec.name}: current [{observed_text}]')

                if len(observed_pairs) == len(target_pairs):
                    max_delta = max(
                        abs(target - current_positions[name])
                        for name, target in target_pairs
                    )
                    if max_delta < 1e-3:
                        self.get_logger().warning(
                            f'{spec.name}: target is effectively identical to /joint_states; '
                            'the robot may not visibly move'
                        )
            else:
                self.get_logger().info(
                    f'{spec.name}: no matching joints found in /joint_states'
                )
        else:
            self.get_logger().info(f'{spec.name}: no /joint_states received yet')

        trajectory = JointTrajectory()
        trajectory.joint_names = list(spec.joint_names)
        point = JointTrajectoryPoint()
        point.positions = list(positions)
        duration = max(0.05, self.duration_s)
        point.time_from_start.sec = int(duration)
        point.time_from_start.nanosec = int((duration % 1.0) * 1e9)
        trajectory.points = [point]

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory
        future = client.send_goal_async(goal)
        future.add_done_callback(
            lambda done, controller_name=spec.name: self._log_goal_result(controller_name, done)
        )
        return f'{spec.name}: sent {len(positions)} joint targets'

    def _log_goal_result(self, controller_name: str, future) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:  # noqa: BLE001 - ROS future can raise transport exceptions.
            self.get_logger().error(f'{controller_name}: failed to send goal: {exc}')
            return
        if not goal_handle.accepted:
            self.get_logger().error(f'{controller_name}: goal rejected')
            return
        self.get_logger().info(f'{controller_name}: goal accepted')


class JointSliderGui:
    def __init__(self, node: JointSliderNode) -> None:
        self.node = node
        self.root = tk.Tk()
        self.root.title('RLLAB Joint Slider GUI')
        self.root.protocol('WM_DELETE_WINDOW', self.close)

        self.slider_vars: dict[str, tk.DoubleVar] = {}
        self.value_labels: dict[str, ttk.Label] = {}
        self.status_var = tk.StringVar(value='Ready. Sliders do not move the robot until you press Send.')
        self.auto_send_var = tk.BooleanVar(value=False)
        self.follow_joint_states_var = tk.BooleanVar(value=False)
        self.dragging_joints: set[str] = set()

        self._build()
        self._sync_sliders_from_joint_states()

    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=8)
        header.pack(fill=tk.X)

        ttk.Label(
            header,
            text=(
                'Set joint targets in radians. Range: '
                f'{self.node.min_position:.2f} to {self.node.max_position:.2f}'
            ),
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            header,
            text='Auto send controller on slider release',
            variable=self.auto_send_var,
        ).pack(anchor=tk.W, pady=(4, 0))
        ttk.Checkbutton(
            header,
            text='Follow live /joint_states',
            variable=self.follow_joint_states_var,
        ).pack(anchor=tk.W, pady=(4, 0))

        buttons = ttk.Frame(header)
        buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(buttons, text='Load Current /joint_states', command=self.load_current_state).pack(
            side=tk.LEFT
        )
        ttk.Button(buttons, text='Send All', command=self.send_all).pack(side=tk.LEFT, padx=(6, 0))

        body = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        body.pack(fill=tk.BOTH, expand=True)

        for spec in self.node.controllers:
            frame = ttk.LabelFrame(body, text=f'{spec.name} -> {spec.action_name}', padding=8)
            frame.pack(fill=tk.X, pady=(8, 0))

            for joint_name in spec.joint_names:
                row = ttk.Frame(frame)
                row.pack(fill=tk.X, pady=1)
                ttk.Label(row, text=joint_name, width=18).pack(side=tk.LEFT)
                var = tk.DoubleVar(value=0.0)
                self.slider_vars[joint_name] = var
                scale = ttk.Scale(
                    row,
                    from_=self.node.min_position,
                    to=self.node.max_position,
                    orient=tk.HORIZONTAL,
                    variable=var,
                    command=lambda _value, name=joint_name: self._update_value_label(name),
                )
                scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
                scale.bind(
                    '<ButtonPress-1>',
                    lambda _event, name=joint_name: self.dragging_joints.add(name),
                )
                scale.bind(
                    '<ButtonRelease-1>',
                    lambda _event, controller=spec.name, name=joint_name: self._on_slider_release(
                        controller, name
                    ),
                )
                value_label = ttk.Label(row, text='0.000', width=8)
                value_label.pack(side=tk.LEFT)
                self.value_labels[joint_name] = value_label

            ttk.Button(
                frame,
                text=f'Send {spec.name}',
                command=lambda controller=spec.name: self.send_controller(controller),
            ).pack(anchor=tk.E, pady=(6, 0))

        footer = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        footer.pack(fill=tk.X)
        ttk.Label(footer, textvariable=self.status_var).pack(anchor=tk.W)

    def _update_value_label(self, joint_name: str) -> None:
        value = self.slider_vars[joint_name].get()
        self.value_labels[joint_name].configure(text=f'{value:.3f}')

    def load_current_state(self) -> None:
        positions = self.node.latest_positions()
        if not positions:
            self.status_var.set('No /joint_states received yet.')
            return

        loaded = self._apply_joint_state_positions(positions, skip_dragging=False)
        self.status_var.set(f'Loaded {loaded} visible joints from /joint_states.')

    def _sync_sliders_from_joint_states(self) -> None:
        if self.follow_joint_states_var.get():
            positions = self.node.latest_positions()
            if positions:
                self._apply_joint_state_positions(positions, skip_dragging=True)
        self.root.after(100, self._sync_sliders_from_joint_states)

    def _apply_joint_state_positions(
        self, positions: dict[str, float], *, skip_dragging: bool
    ) -> int:
        loaded = 0
        min_pos = self.node.min_position
        max_pos = self.node.max_position
        for joint_name, var in self.slider_vars.items():
            if joint_name not in positions:
                continue
            if skip_dragging and joint_name in self.dragging_joints:
                continue
            value = max(min_pos, min(max_pos, positions[joint_name]))
            var.set(value)
            self._update_value_label(joint_name)
            loaded += 1
        return loaded

    def send_all(self) -> None:
        messages = [self.send_controller(spec.name, update_status=False) for spec in self.node.controllers]
        self.status_var.set(' | '.join(messages))

    def send_controller(self, controller_name: str, *, update_status: bool = True) -> str:
        spec = next(spec for spec in self.node.controllers if spec.name == controller_name)
        positions = [self.slider_vars[joint].get() for joint in spec.joint_names]
        message = self.node.send_controller(spec, positions)
        if update_status:
            self.status_var.set(message)
        return message

    def _on_slider_release(self, controller_name: str, joint_name: str) -> None:
        self.dragging_joints.discard(joint_name)
        if self.auto_send_var.get():
            self.send_controller(controller_name)

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        self.root.quit()
        self.root.destroy()


def main(args: list[str] | None = None) -> int:
    rclpy.init(args=args)
    node = JointSliderNode()
    executor_thread = threading.Thread(target=_spin_node, args=(node,), daemon=True)
    executor_thread.start()

    try:
        gui = JointSliderGui(node)
        gui.run()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        executor_thread.join(timeout=1.0)
    return 0


def _spin_node(node: JointSliderNode) -> None:
    try:
        rclpy.spin(node)
    except Exception as exc:  # noqa: BLE001 - suppress shutdown noise from GUI close.
        if rclpy.ok():
            node.get_logger().error(f'ROS spin stopped unexpectedly: {exc}')


if __name__ == '__main__':
    sys.exit(main())
