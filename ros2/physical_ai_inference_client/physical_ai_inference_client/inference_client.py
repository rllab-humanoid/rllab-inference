import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rclpy
from rclpy.parameter import Parameter
import yaml
from ament_index_python.packages import get_package_share_directory
from control_msgs.action import FollowJointTrajectory
from physical_ai_interfaces.msg import TaskInfo
from physical_ai_interfaces.srv import (
    GetRobotTypeList,
    GetSavedPolicyList,
    SendCommand,
    SetRobotType,
)
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.utilities import remove_ros_args
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


@dataclass(frozen=True)
class InitialPoseStepSpec:
    name: str
    positions: tuple[float | None, ...]


@dataclass(frozen=True)
class InitialPoseControllerSpec:
    name: str
    action_topic: str
    joint_states_topic: str
    joint_names: tuple[str, ...]
    step_names: tuple[str, ...]
    steps: tuple[InitialPoseStepSpec, ...]
    duration: float
    position_tolerance: float | None
    velocity_tolerance: float | None


@dataclass(frozen=True)
class InitialPosePlan:
    filename: str
    label: str
    controllers: tuple[InitialPoseControllerSpec, ...]


INITIAL_POSE_CONFIGS = {
    't': ('initial_positions.yaml', 'initial pose'),
    'v': ('initial_positions_full.yaml', 'full initial pose'),
}


class PhysicalAiInferenceClient(Node):
    def __init__(self, policy_path: str | None = None) -> None:
        super().__init__('start_inference')

        self.declare_parameter('service_name', '/task/command')
        self.declare_parameter('saved_policy_list_service_name', '/get_saved_policies')
        self.declare_parameter('get_robot_types_service_name', '/get_robot_types')
        self.declare_parameter('set_robot_type_service_name', '/set_robot_type')
        self.declare_parameter('use_saved_policy_list_service', False)
        self.declare_parameter('robot_type', '')
        self.declare_parameter('task_name', '')
        self.declare_parameter('task_type', 'inference')
        self.declare_parameter('user_id', '')
        self.declare_parameter('task_instruction', [''])
        self.declare_parameter(
            'policy_path',
            '/root/ros2_ws/src/physical_ai_tools/lerobot/outputs/train/putput/'
            'checkpoints/000001/pretrained_model',
        )
        self.declare_parameter('fps', 30)
        self.declare_parameter('tags', ['ffw_bg2_rev4', 'robotis'])
        self.declare_parameter('warmup_time_s', 5)
        self.declare_parameter('episode_time_s', 20)
        self.declare_parameter('reset_time_s', 5)
        self.declare_parameter('num_episodes', 5)
        self.declare_parameter('push_to_hub', True)
        self.declare_parameter('private_mode', False)
        self.declare_parameter('use_optimized_save_mode', True)
        self.declare_parameter('record_inference_mode', False)
        self.declare_parameter('record_rosbag2', False)
        self.declare_parameter('service_wait_timeout_s', 10.0)
        self.declare_parameter('response_timeout_s', 30.0)
        self.declare_parameter('swap_response_timeout_s', 60.0)
        self.declare_parameter('preload_response_timeout_s', 180.0)

        if policy_path:
            self.set_parameters([Parameter('policy_path', value=policy_path)])

        self._service_name = self.get_parameter('service_name').value
        self._saved_policy_list_service_name = self.get_parameter(
            'saved_policy_list_service_name'
        ).value
        self._get_robot_types_service_name = self.get_parameter(
            'get_robot_types_service_name'
        ).value
        self._set_robot_type_service_name = self.get_parameter(
            'set_robot_type_service_name'
        ).value
        self._command_client = self.create_client(SendCommand, self._service_name)
        self._saved_policy_list_client = self.create_client(
            GetSavedPolicyList,
            self._saved_policy_list_service_name,
        )
        self._get_robot_types_client = self.create_client(
            GetRobotTypeList,
            self._get_robot_types_service_name,
        )
        self._set_robot_type_client = self.create_client(
            SetRobotType,
            self._set_robot_type_service_name,
        )
        self._current_policy_path = str(self.get_parameter('policy_path').value)
        self._current_robot_type = str(self.get_parameter('robot_type').value)
        self._pending_policy_path: str | None = None

        self._initial_pose_plans: dict[str, InitialPosePlan | None] = {
            key: self._load_initial_pose_plan(filename, label)
            for key, (filename, label) in INITIAL_POSE_CONFIGS.items()
        }
        self._latest_joint_states: dict[str, JointState | None] = {}
        self._initial_pose_action_clients: dict[str, ActionClient] = {}
        self._initial_pose_state_subscriptions = []
        self._initialize_initial_pose_io()

    def run_console(self) -> bool:
        self.get_logger().info(
            'Interactive inference controller ready. '
            'Input: s=start, f=finish/stop, p=preload, w=swap, '
            'c=cancel preload, t=tabletop initial pose, '
            'v=under-desk initial pose, q=quit'
        )

        while rclpy.ok():
            try:
                command = input(
                    '\n[s] start inference, [f] stop inference, '
                    '[p] preload checkpoint, [w] swap to preloaded, '
                    '[c] cancel preload, '
                    '[t] short initial pose, [v] full initial pose, [q] quit > '
                )
            except (EOFError, KeyboardInterrupt):
                print()
                self.get_logger().info('Exiting interactive controller')
                return True

            command = command.strip().lower()
            if command == 's':
                self._handle_start_input()
            elif command == 'f':
                self.send_finish()
            elif command == 'p':
                self._handle_preload_input()
            elif command == 'w':
                self.send_swap_policy()
            elif command == 'c':
                self.send_cancel_preload()
            elif command == 't':
                self._handle_initial_pose_input('t')
            elif command == 'v':
                self._handle_initial_pose_input('v')
            elif command == 'q':
                self.get_logger().info('Exiting interactive controller')
                return True
            elif command:
                print('Unknown input. Use s, f, p, w, c, t, v, or q.')

        return True

    def _joint_state_callback(self, msg: JointState) -> None:
        self._latest_joint_states['/joint_states'] = msg

    def _make_joint_state_callback(self, topic: str):
        def _callback(msg: JointState) -> None:
            self._latest_joint_states[topic] = msg

        return _callback

    def _initialize_initial_pose_io(self) -> None:
        controller_specs = [
            controller
            for plan in self._initial_pose_plans.values()
            if plan is not None
            for controller in plan.controllers
        ]
        for controller in controller_specs:
            if controller.action_topic not in self._initial_pose_action_clients:
                self._initial_pose_action_clients[controller.action_topic] = ActionClient(
                    self,
                    FollowJointTrajectory,
                    controller.action_topic,
                )
            if controller.joint_states_topic not in self._latest_joint_states:
                self._latest_joint_states[controller.joint_states_topic] = None
                self._initial_pose_state_subscriptions.append(
                    self.create_subscription(
                        JointState,
                        controller.joint_states_topic,
                        self._make_joint_state_callback(controller.joint_states_topic),
                        10,
                    )
                )

    def _load_initial_pose_plan(
        self,
        filename: str,
        label: str,
    ) -> InitialPosePlan | None:
        try:
            pkg_share = get_package_share_directory('physical_ai_inference_client')
            config_path = os.path.join(pkg_share, 'config', filename)
            with open(config_path) as f:
                data = yaml.safe_load(f)
            plan = self._parse_initial_pose_plan(data, filename=filename, label=label)
            if plan is None:
                self.get_logger().warning(
                    f'Could not parse initial pose plan from {config_path}'
                )
                return None
            self.get_logger().info(f'Loaded {filename} from: {config_path}')
            return plan
        except Exception as e:
            self.get_logger().warning(f'Could not load {filename}: {e}')
            return None

    def _handle_initial_pose_input(self, command_key: str) -> None:
        if command_key not in INITIAL_POSE_CONFIGS:
            print(f'Unknown initial pose command: {command_key}')
            return

        plan = self._initial_pose_plans.get(command_key)
        if not plan:
            filename, label = INITIAL_POSE_CONFIGS[command_key]
            print(f'{label.title()} config not loaded. Cannot move to {label}.')
            return

        ordered_step_names = self._ordered_step_names(plan.controllers)
        print(
            f'\nMoving to {plan.label} through '
            f'{len(ordered_step_names)} step(s): {ordered_step_names}'
        )
        for step_name in ordered_step_names:
            step_controllers = [
                controller
                for controller in plan.controllers
                if step_name in controller.step_names
            ]
            if not step_controllers:
                continue
            controller_names = ', '.join(controller.name for controller in step_controllers)
            print(f'  Executing step "{step_name}" together: {controller_names}')
            if not self._execute_initial_pose_step_group(step_name, step_controllers):
                print(f'  Step "{step_name}" failed. Aborting.')
                return
            print(f'  Step "{step_name}" complete.')
        print(f'{plan.label.title()} reached.')

    def _execute_initial_pose_step_group(
        self,
        step_name: str,
        controllers: list[InitialPoseControllerSpec],
    ) -> bool:
        if not controllers:
            return True

        jobs_by_topic: dict[str, list[dict[str, Any]]] = {}
        for controller in controllers:
            positions = self._step_positions_for_controller(controller, step_name)
            if positions is None:
                return False
            jobs_by_topic.setdefault(controller.joint_states_topic, []).append(
                self._build_initial_pose_job(controller, step_name, positions)
            )

        for joint_states_topic, jobs in jobs_by_topic.items():
            js = self._wait_for_joint_state(joint_states_topic)
            if js is None:
                self.get_logger().error(
                    f'Timed out waiting for {joint_states_topic}'
                )
                return False

            prepared_jobs = []
            for job in jobs:
                controller = job['controller']
                start = self._extract_joint_positions(js, list(controller.joint_names))
                if start is None:
                    self.get_logger().error(
                        f'Cannot read joints for {controller.name} from '
                        f'{joint_states_topic}'
                    )
                    return False
                goal = self._build_goal_from_job(job, start)
                if goal is None:
                    return False
                prepared_jobs.append((controller, goal))

            send_jobs = []
            for controller, goal in prepared_jobs:
                client = self._initial_pose_action_clients[controller.action_topic]
                if not client.wait_for_server(timeout_sec=5.0):
                    self.get_logger().error(
                        f'{controller.name} action server not available: '
                        f'{controller.action_topic}'
                    )
                    return False
                send_jobs.append(
                    (
                        controller,
                        controller.duration,
                        client.send_goal_async(goal),
                    )
                )

            if not self._wait_for_goal_acceptance(send_jobs, step_name):
                return False

            if not self._wait_for_goal_results(send_jobs, step_name):
                return False

        return True

    def _build_initial_pose_job(
        self,
        controller: InitialPoseControllerSpec,
        step_name: str,
        positions: tuple[float | None, ...],
    ) -> dict[str, Any]:
        return {
            'controller': controller,
            'step_name': step_name,
            'positions': positions,
        }

    def _build_goal_from_job(
        self,
        job: dict[str, Any],
        start: list[float],
    ) -> FollowJointTrajectory.Goal | None:
        controller: InitialPoseControllerSpec = job['controller']
        step_name: str = job['step_name']
        positions: tuple[float | None, ...] = job['positions']

        if len(positions) != len(controller.joint_names):
            self.get_logger().error(
                f'Step "{step_name}" for {controller.name} has '
                f'{len(positions)} values but {len(controller.joint_names)} joints'
            )
            return None

        target = [
            start_value if target_value is None else target_value
            for start_value, target_value in zip(start, positions)
        ]
        duration = max(0.05, float(controller.duration))

        traj = self._create_smooth_trajectory(
            list(controller.joint_names),
            start,
            target,
            duration,
        )
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = traj
        self._apply_goal_tolerances(goal, controller)
        return goal

    def _step_positions_for_controller(
        self,
        controller: InitialPoseControllerSpec,
        step_name: str,
    ) -> tuple[float | None, ...] | None:
        for step in controller.steps:
            if step.name == step_name:
                return step.positions
        self.get_logger().error(
            f'Step "{step_name}" not found for controller {controller.name}'
        )
        return None

    def _wait_for_goal_acceptance(
        self,
        send_jobs: list[tuple[InitialPoseControllerSpec, float, Any]],
        step_name: str,
    ) -> bool:
        for controller, duration, send_future in send_jobs:
            timeout = max(0.05, float(duration) * 3.0)
            rclpy.spin_until_future_complete(self, send_future, timeout_sec=timeout)
            if not send_future.done() or not send_future.result().accepted:
                self.get_logger().error(
                    f'{controller.name} goal rejected or timed out for step {step_name}'
                )
                return False
        return True

    def _wait_for_goal_results(
        self,
        send_jobs: list[tuple[InitialPoseControllerSpec, float, Any]],
        step_name: str,
    ) -> bool:
        for controller, duration, send_future in send_jobs:
            timeout = max(0.05, float(duration) * 3.0)
            result_future = send_future.result().get_result_async()
            rclpy.spin_until_future_complete(self, result_future, timeout_sec=timeout)
            if not result_future.done():
                self.get_logger().error(
                    f'{controller.name} result timed out for step {step_name}'
                )
                return False
        return True

    def _wait_for_joint_state(
        self,
        joint_states_topic: str,
        timeout_sec: float = 5.0,
    ) -> JointState | None:
        deadline = self.get_clock().now().nanoseconds + int(timeout_sec * 1e9)
        self._latest_joint_states[joint_states_topic] = None
        while self._latest_joint_states[joint_states_topic] is None:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.get_clock().now().nanoseconds > deadline:
                return None
        return self._latest_joint_states[joint_states_topic]

    @staticmethod
    def _apply_goal_tolerances(
        goal: FollowJointTrajectory.Goal,
        controller: InitialPoseControllerSpec,
    ) -> None:
        if hasattr(goal, 'goal_time_tolerance'):
            goal.goal_time_tolerance.sec = 0
            goal.goal_time_tolerance.nanosec = 0

    @staticmethod
    def _parse_initial_pose_plan(
        raw: Any,
        filename: str,
        label: str,
    ) -> InitialPosePlan | None:
        if not isinstance(raw, dict):
            return None

        file_root = raw.get('/**')
        if not isinstance(file_root, dict):
            return None

        controllers: list[InitialPoseControllerSpec] = []
        for controller_name, controller_block in file_root.items():
            if not isinstance(controller_block, dict):
                continue
            params = controller_block.get('ros__parameters')
            if not isinstance(params, dict):
                continue

            joint_names = tuple(
                str(name) for name in params.get('joint_names', []) if name is not None
            )
            step_names = tuple(
                str(step) for step in params.get('step_names', []) if step is not None
            )
            if not joint_names or not step_names:
                continue

            steps: list[InitialPoseStepSpec] = []
            for step_name in step_names:
                positions = params.get(step_name)
                if positions is None:
                    continue
                parsed_positions = PhysicalAiInferenceClient._parse_position_list(
                    positions,
                    len(joint_names),
                )
                if parsed_positions is None:
                    continue
                steps.append(
                    InitialPoseStepSpec(
                        name=step_name,
                        positions=parsed_positions,
                    )
                )

            if not steps:
                continue

            controllers.append(
                InitialPoseControllerSpec(
                    name=controller_name,
                    action_topic=str(
                        params.get(
                            'action_topic',
                            f'/{controller_name}/follow_joint_trajectory',
                        )
                    ),
                    joint_states_topic=str(
                        params.get('joint_states_topic', '/joint_states')
                    ),
                    joint_names=joint_names,
                    step_names=step_names,
                    steps=tuple(steps),
                    duration=float(params.get('duration', 5.0)),
                    position_tolerance=PhysicalAiInferenceClient._optional_float(
                        params.get('position_tolerance')
                    ),
                    velocity_tolerance=PhysicalAiInferenceClient._optional_float(
                        params.get('velocity_tolerance')
                    ),
                )
            )

        if not controllers:
            return None

        return InitialPosePlan(
            filename=filename,
            label=label,
            controllers=tuple(controllers),
        )

    @staticmethod
    def _ordered_step_names(
        controllers: tuple[InitialPoseControllerSpec, ...]
    ) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for controller in controllers:
            for step_name in controller.step_names:
                if step_name in seen:
                    continue
                seen.add(step_name)
                ordered.append(step_name)
        return ordered

    @staticmethod
    def _extract_joint_positions(
        js: JointState, joint_names: list[str]
    ) -> list[float] | None:
        name_list = list(js.name)
        try:
            return [js.position[name_list.index(j)] for j in joint_names]
        except ValueError:
            return None

    @staticmethod
    def _parse_position_list(
        values: Any,
        expected_length: int,
    ) -> tuple[float | None, ...] | None:
        if not isinstance(values, (list, tuple)):
            return None
        if len(values) != expected_length:
            return None

        parsed: list[float | None] = []
        for value in values:
            if value is None:
                parsed.append(None)
                continue
            parsed.append(float(value))
        return tuple(parsed)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _create_smooth_trajectory(
        joint_names: list[str],
        start: list[float],
        end: list[float],
        duration: float,
        num_points: int = 100,
    ) -> JointTrajectory:
        traj = JointTrajectory()
        traj.joint_names = joint_names
        for t in np.linspace(0.0, duration, num_points):
            tn = t / duration
            t2, t3, t4, t5 = tn**2, tn**3, tn**4, tn**5
            pc = 10 * t3 - 15 * t4 + 6 * t5
            vc = (30 * t2 - 60 * t3 + 30 * t4) / duration
            ac = (60 * tn - 180 * t2 + 120 * t3) / (duration**2)
            pt = JointTrajectoryPoint()
            pt.positions     = [s + (e - s) * pc for s, e in zip(start, end)]
            pt.velocities    = [(e - s) * vc      for s, e in zip(start, end)]
            pt.accelerations = [(e - s) * ac      for s, e in zip(start, end)]
            pt.time_from_start.sec     = int(t)
            pt.time_from_start.nanosec = int((t % 1) * 1e9)
            traj.points.append(pt)
        return traj

    def _handle_start_input(self) -> None:
        if not self.select_and_set_robot_type():
            return

        policy_path = self._select_policy_path()
        if not policy_path:
            return

        policy_path = self._resolve_policy_path(policy_path)
        self._current_policy_path = policy_path
        self.set_parameters([Parameter('policy_path', value=policy_path)])
        self.send_start_inference(policy_path=policy_path)

    def _handle_preload_input(self) -> None:
        policy_path = self._select_policy_path()
        if not policy_path:
            return

        policy_path = self._resolve_policy_path(policy_path)
        self.send_preload_policy(policy_path=policy_path)

    def _select_policy_path(self) -> str | None:
        if bool(self.get_parameter('use_saved_policy_list_service').value):
            saved_policies = self.get_saved_policies()
            if not saved_policies:
                return None
            return self._prompt_policy_selection(saved_policies)

        print(
            '\nSkipping /get_saved_policies because the current server can crash '
            'inside that callback.'
        )
        return self._prompt_policy_path()

    def select_and_set_robot_type(self) -> bool:
        robot_types = self.get_robot_types()
        if not robot_types:
            return False

        robot_type = self._prompt_string_selection(
            title='Available robot types:',
            options=robot_types,
            prompt='Select robot type number or exact value (blank=cancel) > ',
        )
        if not robot_type:
            return False

        return self.set_robot_type(robot_type)

    def get_robot_types(self) -> list[str]:
        response = self._call_service(
            client=self._get_robot_types_client,
            request=GetRobotTypeList.Request(),
            service_name=self._get_robot_types_service_name,
        )
        if response is None:
            return []

        if not response.success:
            self.get_logger().error(
                f'Failed to get robot types: {response.message}'
            )
            return []

        robot_types = list(response.robot_types)
        if not robot_types:
            self.get_logger().warning('Robot type list is empty')
            return []

        return robot_types

    def set_robot_type(self, robot_type: str) -> bool:
        request = SetRobotType.Request()
        request.robot_type = robot_type

        self.get_logger().info(f'Setting robot_type: {robot_type}')
        response = self._call_service(
            client=self._set_robot_type_client,
            request=request,
            service_name=self._set_robot_type_service_name,
        )
        if response is None:
            return False

        if response.success:
            self._current_robot_type = robot_type
            self.set_parameters([Parameter('robot_type', value=robot_type)])
            self.get_logger().info(f'Robot type set: {response.message}')
            return True

        self.get_logger().error(f'Failed to set robot type: {response.message}')
        return False

    def get_saved_policies(self) -> list[dict[str, str]]:
        response = self._call_service(
            client=self._saved_policy_list_client,
            request=GetSavedPolicyList.Request(),
            service_name=self._saved_policy_list_service_name,
        )
        if response is None:
            return []

        if not response.success:
            self.get_logger().error(
                f'Failed to get saved policies: {response.message}'
            )
            return []

        saved_policy_paths = list(response.saved_policy_path)
        saved_policy_types = list(response.saved_policy_type)
        if not saved_policy_paths:
            self.get_logger().warning('Saved policy list is empty')
            return []

        saved_policies = []
        for index, path in enumerate(saved_policy_paths):
            policy_type = ''
            if index < len(saved_policy_types):
                policy_type = saved_policy_types[index]
            saved_policies.append({'path': path, 'type': policy_type})

        return saved_policies

    def send_start_inference(self, policy_path: str | None = None) -> bool:
        policy_path = policy_path or self._current_policy_path
        policy_path = self._resolve_policy_path(policy_path)
        self.get_logger().info(f'Selected policy_path: {policy_path}')

        request = self._build_request(
            command=SendCommand.Request.START_INFERENCE,
            policy_path=policy_path,
        )
        self.get_logger().info('Sending START_INFERENCE request')

        response = self._call_service(
            client=self._command_client,
            request=request,
            service_name=self._service_name,
        )
        return self._handle_command_response(response)

    def _resolve_policy_path(self, policy_path: str) -> str:
        # The path refers to a directory on the *server* machine. If this
        # client happens to run on the same host (or a shared docker mount)
        # we can offer the user extra conveniences below — e.g. expanding a
        # training-output directory into selectable checkpoints. Otherwise
        # we send the path verbatim and let the server's _inspect_policy do
        # the real validation.
        path = Path(policy_path).expanduser()
        try:
            path_exists = path.exists()
        except PermissionError:
            self.get_logger().warning(
                'Policy path cannot be inspected on this client (permission '
                f'denied); sending it as-is for the server to validate: '
                f'{policy_path}'
            )
            return policy_path

        if not path_exists:
            self.get_logger().info(
                'Client cannot see this path locally (likely running on a '
                'different host than the server); sending it as-is for the '
                f'server to validate: {policy_path}'
            )
            return policy_path

        if path.name == 'pretrained_model':
            return str(path)

        candidates = self._find_pretrained_model_candidates(path)
        if not candidates:
            self.get_logger().warning(
                'The selected path is not named pretrained_model and no '
                f'checkpoints/*/pretrained_model candidates were found: {path}'
            )
            return str(path)

        print(
            '\nThe selected path looks like a training output directory. '
            'Choose a pretrained_model checkpoint to send:'
        )
        for index, candidate in enumerate(candidates, start=1):
            print(f'  {index}. {candidate}')

        while True:
            selected = input('Select checkpoint number (blank=use original path) > ')
            selected = selected.strip()
            if not selected:
                return str(path)

            if selected.isdigit():
                index = int(selected)
                if 1 <= index <= len(candidates):
                    return str(candidates[index - 1])
                print(f'Choose a number between 1 and {len(candidates)}.')
                continue

            print('Selection must be a number.')

    @staticmethod
    def _find_pretrained_model_candidates(path: Path) -> list[Path]:
        checkpoints_path = path / 'checkpoints'
        if not checkpoints_path.is_dir():
            return []

        candidates = [
            checkpoint / 'pretrained_model'
            for checkpoint in checkpoints_path.iterdir()
            if (checkpoint / 'pretrained_model' / 'config.json').is_file()
        ]
        return sorted(candidates)

    def send_stop(self) -> bool:
        request = self._build_request(
            command=SendCommand.Request.STOP,
            policy_path=self._current_policy_path,
        )
        self.get_logger().info('Sending STOP request')

        response = self._call_service(
            client=self._command_client,
            request=request,
            service_name=self._service_name,
        )
        return self._handle_command_response(response)

    def send_finish(self) -> bool:
        request = self._build_request(
            command=SendCommand.Request.FINISH,
            policy_path=self._current_policy_path,
        )
        self.get_logger().info('Sending FINISH request')

        response = self._call_service(
            client=self._command_client,
            request=request,
            service_name=self._service_name,
        )
        return self._handle_command_response(response)

    def send_preload_policy(self, policy_path: str) -> bool:
        request = self._build_request(
            command=SendCommand.Request.PRELOAD_POLICY,
            policy_path=policy_path,
        )
        self.get_logger().info(
            f'Sending PRELOAD_POLICY request: {policy_path}'
        )
        self.get_logger().info(
            'Waiting for the server to finish loading the policy. '
            'This usually takes several seconds; cancel from another '
            'terminal via /task/command (command=10) if needed.'
        )

        preload_timeout = float(
            self.get_parameter('preload_response_timeout_s').value
        )
        response = self._call_service(
            client=self._command_client,
            request=request,
            service_name=self._service_name,
            response_timeout_s=preload_timeout,
        )
        ok = self._handle_command_response(response)
        if ok:
            self._pending_policy_path = policy_path
        return ok

    def send_swap_policy(self) -> bool:
        request = self._build_request(
            command=SendCommand.Request.SWAP_POLICY,
            policy_path=self._current_policy_path,
        )
        self.get_logger().info('Sending SWAP_POLICY request')

        swap_timeout = float(
            self.get_parameter('swap_response_timeout_s').value
        )
        response = self._call_service(
            client=self._command_client,
            request=request,
            service_name=self._service_name,
            response_timeout_s=swap_timeout,
        )
        ok = self._handle_command_response(response)
        if ok and getattr(self, '_pending_policy_path', None):
            self._current_policy_path = self._pending_policy_path
            self.set_parameters([
                Parameter('policy_path', value=self._current_policy_path)
            ])
            self._pending_policy_path = None
        return ok

    def send_cancel_preload(self) -> bool:
        request = self._build_request(
            command=SendCommand.Request.CANCEL_PRELOAD,
            policy_path=self._current_policy_path,
        )
        if self._pending_policy_path:
            self.get_logger().info(
                f'Cancelling preload of {self._pending_policy_path}'
            )
        else:
            self.get_logger().info(
                'Sending CANCEL_PRELOAD (no client-side record of a '
                'pending policy — checking with server)'
            )

        response = self._call_service(
            client=self._command_client,
            request=request,
            service_name=self._service_name,
        )
        ok = self._handle_command_response(response)
        if ok:
            self._pending_policy_path = None
        return ok

    def _call_service(self, client, request, service_name: str,
                      response_timeout_s: float | None = None):
        service_wait_timeout_s = float(
            self.get_parameter('service_wait_timeout_s').value
        )
        if response_timeout_s is None:
            response_timeout_s = float(
                self.get_parameter('response_timeout_s').value
            )

        self.get_logger().info(f'Waiting for service: {service_name}')
        if not client.wait_for_service(timeout_sec=service_wait_timeout_s):
            self.get_logger().error(
                f'Service not available within {service_wait_timeout_s:.1f}s: '
                f'{service_name}'
            )
            return None

        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=response_timeout_s)

        if not future.done():
            self.get_logger().error(
                f'Service response timed out after {response_timeout_s:.1f}s'
            )
            return None

        response = future.result()
        if response is None:
            self.get_logger().error('Service call failed without a response')
            return None

        return response

    def _handle_command_response(self, response: SendCommand.Response | None) -> bool:
        if response is None:
            return False
        if response.success:
            self.get_logger().info(f'Service accepted command: {response.message}')
            return True

        self.get_logger().error(f'Service rejected command: {response.message}')
        return False

    def _build_request(
        self,
        command: int,
        policy_path: str | None = None,
    ) -> SendCommand.Request:
        request = SendCommand.Request()
        task_info = TaskInfo()

        request.command = command
        policy_path = policy_path or str(self.get_parameter('policy_path').value)

        fields = {
            'task_name': str(self.get_parameter('task_name').value),
            'task_type': str(self.get_parameter('task_type').value),
            'user_id': str(self.get_parameter('user_id').value),
            'task_instruction': self._as_string_list(
                self.get_parameter('task_instruction').value
            ),
            'policy_path': policy_path,
            'fps': int(self.get_parameter('fps').value),
            'tags': self._as_string_list(self.get_parameter('tags').value),
            'warmup_time_s': int(self.get_parameter('warmup_time_s').value),
            'episode_time_s': int(self.get_parameter('episode_time_s').value),
            'reset_time_s': int(self.get_parameter('reset_time_s').value),
            'num_episodes': int(self.get_parameter('num_episodes').value),
            'push_to_hub': bool(self.get_parameter('push_to_hub').value),
            'private_mode': bool(self.get_parameter('private_mode').value),
            'use_optimized_save_mode': bool(
                self.get_parameter('use_optimized_save_mode').value
            ),
            'record_inference_mode': bool(
                self.get_parameter('record_inference_mode').value
            ),
            'record_rosbag2': bool(self.get_parameter('record_rosbag2').value),
        }

        for name, value in fields.items():
            self._set_field_if_present(request, name, value)
            self._set_field_if_present(task_info, name, value)

        self._set_field_if_present(request, 'task_info', task_info)
        return request

    @staticmethod
    def _prompt_policy_selection(saved_policies: list[dict[str, str]]) -> str | None:
        print('\nAvailable saved policy checkpoints:')
        for index, policy in enumerate(saved_policies, start=1):
            policy_type = policy['type'] or 'unknown'
            print(f'  {index}. [{policy_type}] {policy["path"]}')

        while True:
            selected = input('Select policy number or exact path (blank=cancel) > ')
            selected = selected.strip()
            if not selected:
                return None

            if selected.isdigit():
                index = int(selected)
                if 1 <= index <= len(saved_policies):
                    return saved_policies[index - 1]['path']
                print(f'Choose a number between 1 and {len(saved_policies)}.')
                continue

            paths = [policy['path'] for policy in saved_policies]
            if selected in paths:
                return selected

            print('Selection is not in the saved policy list.')

    @staticmethod
    def _prompt_policy_path() -> str | None:
        while True:
            policy_path = input('Enter policy checkpoint path (blank=cancel) > ')
            policy_path = policy_path.strip()
            if not policy_path:
                return None
            return policy_path

    @staticmethod
    def _prompt_string_selection(
        title: str,
        options: list[str],
        prompt: str,
    ) -> str | None:
        print(f'\n{title}')
        for index, option in enumerate(options, start=1):
            print(f'  {index}. {option}')

        while True:
            selected = input(prompt).strip()
            if not selected:
                return None

            if selected.isdigit():
                index = int(selected)
                if 1 <= index <= len(options):
                    return options[index - 1]
                print(f'Choose a number between 1 and {len(options)}.')
                continue

            if selected in options:
                return selected

            print('Selection is not in the list.')

    @staticmethod
    def _set_field_if_present(message: Any, name: str, value: Any) -> None:
        if name in message.get_fields_and_field_types():
            setattr(message, name, value)

    @staticmethod
    def _as_string_list(value: Any) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        if value is None:
            return []
        return [str(value)]


def main(args: list[str] | None = None) -> int:
    raw_args = sys.argv if args is None else args
    non_ros_args = remove_ros_args(args=raw_args)[1:]
    policy_path = non_ros_args[0] if non_ros_args else None

    if len(non_ros_args) > 1:
        print(
            'Usage: ros2 run physical_ai_inference_client start_inference '
            '[policy_path]',
            file=sys.stderr,
        )
        return 2

    rclpy.init(args=args)
    node = PhysicalAiInferenceClient(policy_path=policy_path)

    try:
        if policy_path:
            success = (
                node.select_and_set_robot_type()
                and node.send_start_inference(policy_path=policy_path)
            )
        else:
            success = node.run_console()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
