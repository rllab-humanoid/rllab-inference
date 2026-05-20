"""Shared fixtures for inference_client tests.

Reuses the FakeNode / sys.modules stubbing pattern established by
``test_start_inference_initial_pose_modes.py``.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


# ---- Fakes ------------------------------------------------------------------

class FakeParameter:
    def __init__(self, value):
        self.value = value


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(('info', message))

    def error(self, message):
        self.messages.append(('error', message))

    def warning(self, message):
        self.messages.append(('warning', message))


class FakeClock:
    def now(self):
        return types.SimpleNamespace(nanoseconds=0)


class _CapturedFuture:
    """Future object whose ``result()`` returns a configurable response."""
    def __init__(self, response):
        self._response = response

    def done(self):
        return True

    def result(self):
        return self._response


class CapturingClient:
    """A service client mock that records every call_async invocation."""
    def __init__(self, service_type, service_name):
        self.service_type = service_type
        self.service_name = service_name
        self.calls = []
        # response programmable via response_factory
        self.response_factory = lambda req: types.SimpleNamespace(
            success=True, message='ok')

    def wait_for_service(self, timeout_sec):
        return True

    def call_async(self, request):
        self.calls.append(request)
        return _CapturedFuture(self.response_factory(request))


class FakeNode:
    def __init__(self, name):
        self.name = name
        self.parameters = {}
        self.logger = FakeLogger()
        self.clients = []
        self.subscriptions = []
        self.clock = FakeClock()

    def declare_parameter(self, name, default_value):
        self.parameters[name] = default_value

    def get_parameter(self, name):
        return FakeParameter(self.parameters[name])

    def set_parameters(self, params):
        for param in params:
            self.parameters[param.name] = param.value
        return params

    def create_client(self, service_type, service_name):
        client = CapturingClient(service_type, service_name)
        self.clients.append(client)
        return client

    def create_subscription(self, msg_type, topic, callback, qos):
        self.subscriptions.append((msg_type, topic, callback, qos))
        return callback

    def get_logger(self):
        return self.logger

    def get_clock(self):
        return self.clock

    def destroy_node(self):
        pass


# ---- TaskInfo / SendCommand stubs ------------------------------------------

class DummyTaskInfo:
    def __init__(self):
        self.policy_path = ''
        self.task_name = ''
        self.task_type = ''
        self.user_id = ''
        self.task_instruction = []
        self.fps = 0
        self.tags = []
        self.warmup_time_s = 0
        self.episode_time_s = 0
        self.reset_time_s = 0
        self.num_episodes = 0
        self.push_to_hub = False
        self.private_mode = False
        self.use_optimized_save_mode = False
        self.record_inference_mode = False
        self.record_rosbag2 = False

    def get_fields_and_field_types(self):
        return {
            'policy_path': 'string',
            'task_name': 'string',
            'task_type': 'string',
            'user_id': 'string',
            'task_instruction': 'sequence<string>',
            'fps': 'uint8',
            'tags': 'sequence<string>',
            'warmup_time_s': 'uint16',
            'episode_time_s': 'uint16',
            'reset_time_s': 'uint16',
            'num_episodes': 'uint16',
            'push_to_hub': 'boolean',
            'private_mode': 'boolean',
            'use_optimized_save_mode': 'boolean',
            'record_inference_mode': 'boolean',
            'record_rosbag2': 'boolean',
        }


class DummySendCommandRequest:
    # all 11 command constants
    IDLE = 0
    START_RECORD = 1
    START_INFERENCE = 2
    STOP = 3
    MOVE_TO_NEXT = 4
    RERECORD = 5
    FINISH = 6
    SKIP_TASK = 7
    PRELOAD_POLICY = 8
    SWAP_POLICY = 9
    CANCEL_PRELOAD = 10

    def __init__(self):
        self.command = 0
        self.task_info = DummyTaskInfo()
        self.policy_path = ''
        self.task_name = ''
        self.task_type = ''
        self.user_id = ''
        self.task_instruction = []
        self.fps = 0
        self.tags = []
        self.warmup_time_s = 0
        self.episode_time_s = 0
        self.reset_time_s = 0
        self.num_episodes = 0
        self.push_to_hub = False
        self.private_mode = False
        self.use_optimized_save_mode = False
        self.record_inference_mode = False
        self.record_rosbag2 = False

    def get_fields_and_field_types(self):
        return {
            'command': 'uint8',
            'task_info': 'physical_ai_interfaces/TaskInfo',
            **DummyTaskInfo().get_fields_and_field_types(),
        }


class DummySendCommandResponse:
    def __init__(self, success=True, message='ok'):
        self.success = success
        self.message = message


class DummySendCommand:
    Request = DummySendCommandRequest
    Response = DummySendCommandResponse


class DummyEmptyService:
    """Generic empty request/response for get_*_list services."""
    class Request:
        def __init__(self):
            pass
        def get_fields_and_field_types(self):
            return {}
    class Response:
        def __init__(self):
            self.success = True
            self.message = ''
            self.robot_types = []
            self.saved_policy_path = []
            self.saved_policy_type = []
        def get_fields_and_field_types(self):
            return {}


class DummySetRobotTypeRequest:
    def __init__(self):
        self.robot_type = ''
    def get_fields_and_field_types(self):
        return {'robot_type': 'string'}


class DummySetRobotType:
    Request = DummySetRobotTypeRequest
    class Response:
        def __init__(self):
            self.success = True
            self.message = 'ok'


# ---- Helpers ----------------------------------------------------------------

def install_ros_stubs(share_root: Path):
    rclpy = types.ModuleType('rclpy')
    rclpy.init = lambda args=None: None
    rclpy.ok = lambda: True
    rclpy.shutdown = lambda: None
    rclpy.spin = lambda node: None
    rclpy.spin_once = lambda node, timeout_sec=None: None
    rclpy.spin_until_future_complete = (
        lambda node, future, timeout_sec=None: None)

    rclpy_node = types.ModuleType('rclpy.node')
    rclpy_node.Node = FakeNode
    rclpy.node = rclpy_node

    rclpy_action = types.ModuleType('rclpy.action')

    class _ActionClient:
        def __init__(self, *a, **k):
            pass
        def wait_for_server(self, timeout_sec):
            return True

    rclpy_action.ActionClient = _ActionClient
    rclpy.action = rclpy_action

    rclpy_parameter = types.ModuleType('rclpy.parameter')

    class _Parameter:
        def __init__(self, name=None, value=None, **kw):
            # support both Parameter(name, value=X) and Parameter('policy_path', value=...)
            self.name = name if isinstance(name, str) else (kw.get('name') or '')
            self.value = value if value is not None else kw.get('value')

    rclpy_parameter.Parameter = _Parameter
    rclpy.parameter = rclpy_parameter

    rclpy_utilities = types.ModuleType('rclpy.utilities')
    rclpy_utilities.remove_ros_args = lambda args=None: [args or []]
    rclpy.utilities = rclpy_utilities

    ament = types.ModuleType('ament_index_python')
    ament_pkg = types.ModuleType('ament_index_python.packages')
    ament_pkg.get_package_share_directory = (
        lambda package_name: str(share_root))
    ament.packages = ament_pkg

    control_msgs = types.ModuleType('control_msgs')
    control_msgs_action = types.ModuleType('control_msgs.action')
    class _FJT:
        class Goal:
            def __init__(self):
                self.trajectory = None
                self.goal_time_tolerance = types.SimpleNamespace(
                    sec=0, nanosec=0)
    control_msgs_action.FollowJointTrajectory = _FJT
    control_msgs.action = control_msgs_action

    physical_ai_interfaces = types.ModuleType('physical_ai_interfaces')
    pi_msg = types.ModuleType('physical_ai_interfaces.msg')
    pi_msg.TaskInfo = DummyTaskInfo
    physical_ai_interfaces.msg = pi_msg
    pi_srv = types.ModuleType('physical_ai_interfaces.srv')
    pi_srv.GetRobotTypeList = DummyEmptyService
    pi_srv.GetSavedPolicyList = DummyEmptyService
    pi_srv.SendCommand = DummySendCommand
    pi_srv.SetRobotType = DummySetRobotType
    physical_ai_interfaces.srv = pi_srv

    sensor_msgs = types.ModuleType('sensor_msgs')
    sensor_msg = types.ModuleType('sensor_msgs.msg')
    class _JointState:
        def __init__(self, name=None, position=None):
            self.name = name or []
            self.position = position or []
    sensor_msg.JointState = _JointState
    sensor_msgs.msg = sensor_msg

    trajectory_msgs = types.ModuleType('trajectory_msgs')
    traj_msg = types.ModuleType('trajectory_msgs.msg')
    class _JT:
        def __init__(self):
            self.joint_names = []
            self.points = []
    class _JTP:
        def __init__(self):
            self.positions = []
            self.velocities = []
            self.accelerations = []
            self.time_from_start = types.SimpleNamespace(sec=0, nanosec=0)
    traj_msg.JointTrajectory = _JT
    traj_msg.JointTrajectoryPoint = _JTP
    trajectory_msgs.msg = traj_msg

    modules = {
        'rclpy': rclpy,
        'rclpy.node': rclpy_node,
        'rclpy.action': rclpy_action,
        'rclpy.parameter': rclpy_parameter,
        'rclpy.utilities': rclpy_utilities,
        'ament_index_python': ament,
        'ament_index_python.packages': ament_pkg,
        'control_msgs': control_msgs,
        'control_msgs.action': control_msgs_action,
        'physical_ai_interfaces': physical_ai_interfaces,
        'physical_ai_interfaces.msg': pi_msg,
        'physical_ai_interfaces.srv': pi_srv,
        'sensor_msgs': sensor_msgs,
        'sensor_msgs.msg': sensor_msg,
        'trajectory_msgs': trajectory_msgs,
        'trajectory_msgs.msg': traj_msg,
    }
    sys.modules.update(modules)


def import_inference_client(share_root: Path):
    install_ros_stubs(share_root)
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    sys.modules.pop(
        'physical_ai_inference_client.inference_client', None)
    return importlib.import_module(
        'physical_ai_inference_client.inference_client')


@pytest.fixture
def client_module(tmp_path):
    share_root = tmp_path / 'share' / 'physical_ai_inference_client'
    (share_root / 'config').mkdir(parents=True)
    # provide minimal initial position yamls so __init__ doesn't error
    (share_root / 'config' / 'initial_positions.yaml').write_text('{}\n')
    (share_root / 'config' / 'initial_positions_full.yaml').write_text('{}\n')
    return import_inference_client(share_root)


@pytest.fixture
def make_client(client_module):
    """Return a freshly constructed PhysicalAiInferenceClient."""
    def _make(**param_overrides):
        node = client_module.PhysicalAiInferenceClient()
        for k, v in param_overrides.items():
            node.parameters[k] = v
        return node
    return _make
