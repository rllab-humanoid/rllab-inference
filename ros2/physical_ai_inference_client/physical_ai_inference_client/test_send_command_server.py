import json
from typing import Any

import rclpy
from physical_ai_interfaces.msg import TaskInfo
from physical_ai_interfaces.srv import (
    GetRobotTypeList,
    GetSavedPolicyList,
    SendCommand,
    SetRobotType,
)
from rclpy.node import Node


class TestSendCommandServer(Node):
    def __init__(self) -> None:
        super().__init__('test_send_command_server')

        self.declare_parameter('service_name', '/task/command')
        self.declare_parameter('saved_policy_list_service_name', '/get_saved_policies')
        self.declare_parameter('get_robot_types_service_name', '/get_robot_types')
        self.declare_parameter('set_robot_type_service_name', '/set_robot_type')
        self.declare_parameter('robot_types', ['ffw_bg2_rev4'])
        self.declare_parameter('saved_policy_path', ['/tmp/test_policy'])
        self.declare_parameter('saved_policy_type', ['act'])
        self.declare_parameter('expected_policy_path', '')
        self.declare_parameter('shutdown_after_request', False)

        self._service_name = str(self.get_parameter('service_name').value)
        self._saved_policy_list_service_name = str(
            self.get_parameter('saved_policy_list_service_name').value
        )
        self._get_robot_types_service_name = str(
            self.get_parameter('get_robot_types_service_name').value
        )
        self._set_robot_type_service_name = str(
            self.get_parameter('set_robot_type_service_name').value
        )
        self._robot_types = [
            str(robot_type) for robot_type in self.get_parameter('robot_types').value
        ]
        self._saved_policy_path = [
            str(path) for path in self.get_parameter('saved_policy_path').value
        ]
        self._saved_policy_type = [
            str(policy_type)
            for policy_type in self.get_parameter('saved_policy_type').value
        ]
        self._expected_policy_path = str(
            self.get_parameter('expected_policy_path').value
        )
        self._shutdown_after_request = bool(
            self.get_parameter('shutdown_after_request').value
        )
        self._selected_robot_type = ''
        self.handled_request = False

        self.create_service(SendCommand, self._service_name, self._handle_request)
        self.create_service(
            GetSavedPolicyList,
            self._saved_policy_list_service_name,
            self._handle_saved_policy_list_request,
        )
        self.create_service(
            GetRobotTypeList,
            self._get_robot_types_service_name,
            self._handle_get_robot_types_request,
        )
        self.create_service(
            SetRobotType,
            self._set_robot_type_service_name,
            self._handle_set_robot_type_request,
        )
        self.get_logger().info(f'Test SendCommand service ready: {self._service_name}')
        self.get_logger().info(
            'Test GetSavedPolicyList service ready: '
            f'{self._saved_policy_list_service_name}'
        )
        self.get_logger().info(
            'Test GetRobotTypeList service ready: '
            f'{self._get_robot_types_service_name}'
        )
        self.get_logger().info(
            f'Test SetRobotType service ready: {self._set_robot_type_service_name}'
        )
        if self._expected_policy_path:
            self.get_logger().info(
                f'Expected policy_path: {self._expected_policy_path}'
            )

    def _handle_get_robot_types_request(
        self,
        request: GetRobotTypeList.Request,
        response: GetRobotTypeList.Response,
    ) -> GetRobotTypeList.Response:
        del request
        response.robot_types = self._robot_types
        response.success = bool(self._robot_types)
        response.message = (
            'Robot type list retrieved successfully'
            if response.success
            else 'No robot types available'
        )
        self.get_logger().info(f'Returning robot_types: {self._robot_types}')
        return response

    def _handle_set_robot_type_request(
        self,
        request: SetRobotType.Request,
        response: SetRobotType.Response,
    ) -> SetRobotType.Response:
        if request.robot_type in self._robot_types:
            self._selected_robot_type = request.robot_type
            response.success = True
            response.message = f'Robot type set to {request.robot_type}'
            self.get_logger().info(response.message)
        else:
            response.success = False
            response.message = f'Unknown robot type: {request.robot_type}'
            self.get_logger().error(response.message)
        return response

    def _handle_saved_policy_list_request(
        self,
        request: GetSavedPolicyList.Request,
        response: GetSavedPolicyList.Response,
    ) -> GetSavedPolicyList.Response:
        del request
        response.saved_policy_path = self._saved_policy_path
        response.saved_policy_type = self._saved_policy_type
        response.success = bool(self._saved_policy_path)
        response.message = (
            'Saved policies retrieved successfully'
            if response.success
            else 'No saved policies available'
        )
        self.get_logger().info(
            f'Returning saved_policy_path: {self._saved_policy_path}'
        )
        return response

    def _handle_request(
        self,
        request: SendCommand.Request,
        response: SendCommand.Response,
    ) -> SendCommand.Response:
        summary = self._request_summary(request)
        self.get_logger().info(
            'Received SendCommand request:\n'
            f'{json.dumps(summary, indent=2, ensure_ascii=False)}'
        )

        errors = self._validate_request(request)
        response.success = not errors
        response.message = 'request matched expected inference command'
        if errors:
            response.message = '; '.join(errors)
            self.get_logger().error(f'Request validation failed: {response.message}')
        else:
            self.get_logger().info('Request validation succeeded')

        self.handled_request = True
        return response

    def _validate_request(self, request: SendCommand.Request) -> list[str]:
        errors = []
        task_info = self._task_info(request)

        if not self._selected_robot_type:
            errors.append('robot_type was not set before command')

        valid_commands = [
            SendCommand.Request.START_INFERENCE,
            SendCommand.Request.STOP,
            SendCommand.Request.FINISH,
        ]
        if request.command not in valid_commands:
            errors.append(
                'command='
                f'{request.command}, expected START_INFERENCE, STOP, or FINISH'
            )

        if (
            request.command == SendCommand.Request.START_INFERENCE
            and task_info.task_type != 'inference'
        ):
            errors.append(f'task_type={task_info.task_type}, expected inference')

        if (
            request.command == SendCommand.Request.START_INFERENCE
            and self._expected_policy_path
        ):
            if task_info.policy_path != self._expected_policy_path:
                errors.append(
                    'policy_path='
                    f'{task_info.policy_path}, expected {self._expected_policy_path}'
                )

        return errors

    def _request_summary(self, request: SendCommand.Request) -> dict[str, Any]:
        task_info = self._task_info(request)
        return {
            'command': request.command,
            'command_name': self._command_name(request.command),
            'task_info': {
                'task_name': task_info.task_name,
                'task_type': task_info.task_type,
                'user_id': task_info.user_id,
                'task_instruction': list(task_info.task_instruction),
                'policy_path': task_info.policy_path,
                'fps': task_info.fps,
                'tags': list(task_info.tags),
                'warmup_time_s': task_info.warmup_time_s,
                'episode_time_s': task_info.episode_time_s,
                'reset_time_s': task_info.reset_time_s,
                'num_episodes': task_info.num_episodes,
                'push_to_hub': task_info.push_to_hub,
                'private_mode': task_info.private_mode,
                'use_optimized_save_mode': task_info.use_optimized_save_mode,
                'record_inference_mode': task_info.record_inference_mode,
                'record_rosbag2': task_info.record_rosbag2,
            },
        }

    @staticmethod
    def _task_info(request: SendCommand.Request) -> TaskInfo:
        return request.task_info

    @staticmethod
    def _command_name(command: int) -> str:
        names = {
            SendCommand.Request.IDLE: 'IDLE',
            SendCommand.Request.START_RECORD: 'START_RECORD',
            SendCommand.Request.START_INFERENCE: 'START_INFERENCE',
            SendCommand.Request.STOP: 'STOP',
            SendCommand.Request.MOVE_TO_NEXT: 'MOVE_TO_NEXT',
            SendCommand.Request.RERECORD: 'RERECORD',
            SendCommand.Request.FINISH: 'FINISH',
            SendCommand.Request.SKIP_TASK: 'SKIP_TASK',
        }
        return names.get(command, 'UNKNOWN')


def main(args: list[str] | None = None) -> int:
    rclpy.init(args=args)
    node = TestSendCommandServer()

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            if node.handled_request and node._shutdown_after_request:
                break
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
