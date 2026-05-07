import sys
from pathlib import Path
from typing import Any

import rclpy
from rclpy.parameter import Parameter
from physical_ai_interfaces.msg import TaskInfo
from physical_ai_interfaces.srv import (
    GetRobotTypeList,
    GetSavedPolicyList,
    SendCommand,
    SetRobotType,
)
from rclpy.node import Node
from rclpy.utilities import remove_ros_args


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

    def run_console(self) -> bool:
        self.get_logger().info(
            'Interactive inference controller ready. '
            'Input: s=start, f=finish/stop, q=quit'
        )

        while rclpy.ok():
            try:
                command = input('\n[s] start inference, [f] stop inference, [q] quit > ')
            except (EOFError, KeyboardInterrupt):
                print()
                self.get_logger().info('Exiting interactive controller')
                return True

            command = command.strip().lower()
            if command == 's':
                self._handle_start_input()
            elif command == 'f':
                self.send_finish()
            elif command == 'q':
                self.get_logger().info('Exiting interactive controller')
                return True
            elif command:
                print('Unknown input. Use s, f, or q.')

        return True

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
        path = Path(policy_path).expanduser()
        try:
            path_exists = path.exists()
        except PermissionError:
            self.get_logger().warning(
                'Policy path cannot be inspected from this client due to '
                f'permission restrictions; sending it as-is: {policy_path}'
            )
            return policy_path

        if not path_exists:
            self.get_logger().warning(
                'Policy path is not visible from this client machine; sending it '
                f'as-is: {policy_path}'
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

    def _call_service(self, client, request, service_name: str):
        service_wait_timeout_s = float(
            self.get_parameter('service_wait_timeout_s').value
        )
        response_timeout_s = float(self.get_parameter('response_timeout_s').value)

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
