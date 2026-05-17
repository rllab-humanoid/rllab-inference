from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


class FakeParameter:
    def __init__(self, value):
        self.value = value


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def error(self, message):
        self.messages.append(("error", message))

    def warning(self, message):
        self.messages.append(("warning", message))


class FakeClock:
    def now(self):
        return types.SimpleNamespace(nanoseconds=0)


class FakeNode:
    def __init__(self, name):
        self.name = name
        self.parameters = {}
        self.logger = FakeLogger()
        self.clients = []
        self.subscriptions = []
        self.clock = FakeClock()
        self.call_log = []

    def declare_parameter(self, name, default_value):
        self.parameters[name] = default_value

    def get_parameter(self, name):
        return FakeParameter(self.parameters[name])

    def set_parameters(self, params):
        for param in params:
            self.parameters[param.name] = param.value
        return params

    def create_client(self, service_type, service_name):
        client = types.SimpleNamespace(
            service_type=service_type,
            service_name=service_name,
            wait_for_service=lambda timeout_sec: True,
            call_async=lambda request: types.SimpleNamespace(
                done=lambda: True,
                result=lambda: types.SimpleNamespace(success=True, message="ok"),
            ),
        )
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


class FakeActionClient:
    def __init__(self, node, action_type, action_name):
        self.node = node
        self.action_type = action_type
        self.action_name = action_name

    def wait_for_server(self, timeout_sec):
        self.node.call_log.append(("wait", self.action_name))
        return True

    def send_goal_async(self, goal):
        self.node.call_log.append(("send", self.action_name, tuple(goal.trajectory.joint_names)))
        return FakeSendFuture()


class FakeResultFuture:
    def done(self):
        return True

    def result(self):
        return types.SimpleNamespace()


class FakeGoalHandle:
    def __init__(self):
        self.accepted = True

    def get_result_async(self):
        return FakeResultFuture()


class FakeSendFuture:
    def done(self):
        return True

    def result(self):
        return FakeGoalHandle()


class FakeJointState:
    def __init__(self, name=None, position=None):
        self.name = name or []
        self.position = position or []


class FakeJointTrajectory:
    def __init__(self):
        self.joint_names = []
        self.points = []


class FakeJointTrajectoryPoint:
    def __init__(self):
        self.positions = []
        self.velocities = []
        self.accelerations = []
        self.time_from_start = types.SimpleNamespace(sec=0, nanosec=0)


class FakeFollowJointTrajectory:
    class Goal:
        def __init__(self):
            self.trajectory = None
            self.goal_time_tolerance = types.SimpleNamespace(sec=0, nanosec=0)


class DummyTaskInfo:
    def get_fields_and_field_types(self):
        return {}


class DummyRequest:
    START_INFERENCE = 1
    STOP = 2
    FINISH = 3

    def get_fields_and_field_types(self):
        return {}


class DummyResponse:
    def __init__(self):
        self.success = True
        self.message = "ok"


class DummyService:
    Request = DummyRequest
    Response = DummyResponse


def install_ros_stubs(share_root: Path):
    rclpy = types.ModuleType("rclpy")
    rclpy.init = lambda args=None: None
    rclpy.ok = lambda: True
    rclpy.shutdown = lambda: None
    rclpy.spin = lambda node: None
    rclpy.spin_once = lambda node, timeout_sec=None: None
    rclpy.spin_until_future_complete = lambda node, future, timeout_sec=None: None

    rclpy_node = types.ModuleType("rclpy.node")
    rclpy_node.Node = FakeNode
    rclpy.node = rclpy_node

    rclpy_action = types.ModuleType("rclpy.action")
    rclpy_action.ActionClient = FakeActionClient
    rclpy.action = rclpy_action

    rclpy_parameter = types.ModuleType("rclpy.parameter")
    rclpy_parameter.Parameter = type("Parameter", (), {})
    rclpy.parameter = rclpy_parameter

    rclpy_utilities = types.ModuleType("rclpy.utilities")
    rclpy_utilities.remove_ros_args = lambda args=None: [args or []]
    rclpy.utilities = rclpy_utilities

    ament_index_python = types.ModuleType("ament_index_python")
    ament_index_packages = types.ModuleType("ament_index_python.packages")
    ament_index_packages.get_package_share_directory = lambda package_name: str(share_root)
    ament_index_python.packages = ament_index_packages

    control_msgs = types.ModuleType("control_msgs")
    control_msgs_action = types.ModuleType("control_msgs.action")
    control_msgs_action.FollowJointTrajectory = FakeFollowJointTrajectory
    control_msgs.action = control_msgs_action

    physical_ai_interfaces = types.ModuleType("physical_ai_interfaces")
    physical_ai_interfaces_msg = types.ModuleType("physical_ai_interfaces.msg")
    physical_ai_interfaces_msg.TaskInfo = DummyTaskInfo
    physical_ai_interfaces.msg = physical_ai_interfaces_msg
    physical_ai_interfaces_srv = types.ModuleType("physical_ai_interfaces.srv")
    physical_ai_interfaces_srv.GetRobotTypeList = DummyService
    physical_ai_interfaces_srv.GetSavedPolicyList = DummyService
    physical_ai_interfaces_srv.SendCommand = DummyService
    physical_ai_interfaces_srv.SetRobotType = DummyService
    physical_ai_interfaces.srv = physical_ai_interfaces_srv

    sensor_msgs = types.ModuleType("sensor_msgs")
    sensor_msgs_msg = types.ModuleType("sensor_msgs.msg")
    sensor_msgs_msg.JointState = FakeJointState
    sensor_msgs.msg = sensor_msgs_msg

    trajectory_msgs = types.ModuleType("trajectory_msgs")
    trajectory_msgs_msg = types.ModuleType("trajectory_msgs.msg")
    trajectory_msgs_msg.JointTrajectory = FakeJointTrajectory
    trajectory_msgs_msg.JointTrajectoryPoint = FakeJointTrajectoryPoint
    trajectory_msgs.msg = trajectory_msgs_msg

    modules = {
        "rclpy": rclpy,
        "rclpy.node": rclpy_node,
        "rclpy.action": rclpy_action,
        "rclpy.parameter": rclpy_parameter,
        "rclpy.utilities": rclpy_utilities,
        "ament_index_python": ament_index_python,
        "ament_index_python.packages": ament_index_packages,
        "control_msgs": control_msgs,
        "control_msgs.action": control_msgs_action,
        "physical_ai_interfaces": physical_ai_interfaces,
        "physical_ai_interfaces.msg": physical_ai_interfaces_msg,
        "physical_ai_interfaces.srv": physical_ai_interfaces_srv,
        "sensor_msgs": sensor_msgs,
        "sensor_msgs.msg": sensor_msgs_msg,
        "trajectory_msgs": trajectory_msgs,
        "trajectory_msgs.msg": trajectory_msgs_msg,
    }
    sys.modules.update(modules)


def import_inference_client(share_root: Path):
    install_ros_stubs(share_root)
    package_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(package_root))
    sys.modules.pop("physical_ai_inference_client.inference_client", None)
    return importlib.import_module("physical_ai_inference_client.inference_client")


def test_console_prompt_mentions_v(monkeypatch, tmp_path):
    share_root = tmp_path / "share" / "physical_ai_inference_client"
    (share_root / "config").mkdir(parents=True)
    (share_root / "config" / "initial_positions.yaml").write_text(
        "/**:\n"
        "  arm_l_joint_trajectory_executor:\n"
        "    ros__parameters:\n"
        "      joint_names: [arm_l_joint1]\n"
        "      step_names: [target]\n"
        "      target: [0.0]\n"
        "      duration: 1.0\n"
        "      action_topic: /arm_l_controller/follow_joint_trajectory\n"
        "      joint_states_topic: /joint_states\n",
        encoding="utf-8",
    )
    (share_root / "config" / "initial_positions_full.yaml").write_text(
        "/**:\n"
        "  arm_l_joint_trajectory_executor:\n"
        "    ros__parameters:\n"
        "      joint_names: [arm_l_joint1]\n"
        "      step_names: [home, test1]\n"
        "      home: [0.0]\n"
        "      test1: [0.5]\n"
        "      duration: 2.0\n"
        "      action_topic: /arm_l_controller/follow_joint_trajectory\n"
        "      joint_states_topic: /joint_states\n",
        encoding="utf-8",
    )

    module = import_inference_client(share_root)
    node = module.PhysicalAiInferenceClient()

    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)

    assert node.run_console() is True
    assert any("[v] full initial pose" in prompt for prompt in prompts)
    assert (
        "info",
        "Interactive inference controller ready. Input: s=start, f=finish/stop, "
        "t=tabletop initial pose, v=under-desk initial pose, q=quit",
    ) in node.logger.messages


def test_t_and_v_parse_separate_ros_parameter_pose_configs(tmp_path):
    share_root = tmp_path / "share" / "physical_ai_inference_client"
    config_dir = share_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "initial_positions.yaml").write_text(
        "/**:\n"
        "  arm_l_joint_trajectory_executor:\n"
        "    ros__parameters:\n"
        "      joint_names:\n"
        "        - arm_l_joint1\n"
        "        - arm_l_joint2\n"
        "      step_names: [target]\n"
        "      target: [-1.5, 0.0]\n"
        "      duration: 5.0\n"
        "      action_topic: /arm_l_controller/follow_joint_trajectory\n"
        "      joint_states_topic: /joint_states\n"
        "  head_joint_trajectory_executor:\n"
        "    ros__parameters:\n"
        "      joint_names:\n"
        "        - head_joint1\n"
        "        - head_joint2\n"
        "      step_names: [home]\n"
        "      home: [0.44, 0.0981]\n"
        "      duration: 5.0\n"
        "      action_topic: /head_controller/follow_joint_trajectory\n"
        "      joint_states_topic: /joint_states\n",
        encoding="utf-8",
    )
    (config_dir / "initial_positions_full.yaml").write_text(
        "/**:\n"
        "  arm_r_joint_trajectory_executor:\n"
        "    ros__parameters:\n"
        "      joint_names:\n"
        "        - arm_r_joint1\n"
        "        - arm_r_joint2\n"
        "      step_names: [home, test1, test2]\n"
        "      home: [0.0, 0.0]\n"
        "      test1: [0.0, -0.75]\n"
        "      test2: [0.0, -1.4]\n"
        "      duration: 5.0\n"
        "      action_topic: /arm_r_controller/follow_joint_trajectory\n"
        "      joint_states_topic: /joint_states\n"
        "  lift_joint_trajectory_executor:\n"
        "    ros__parameters:\n"
        "      joint_names: [lift_joint]\n"
        "      step_names: [home]\n"
        "      home: [-0.15]\n"
        "      duration: 10.0\n"
        "      action_topic: /lift_controller/follow_joint_trajectory\n"
        "      joint_states_topic: /joint_states\n",
        encoding="utf-8",
    )

    module = import_inference_client(share_root)
    node = module.PhysicalAiInferenceClient()

    t_plan = node._initial_pose_plans["t"]
    v_plan = node._initial_pose_plans["v"]
    assert t_plan is not None
    assert v_plan is not None

    assert [controller.name for controller in t_plan.controllers] == [
        "arm_l_joint_trajectory_executor",
        "head_joint_trajectory_executor",
    ]
    assert t_plan.controllers[0].step_names == ("target",)
    assert t_plan.controllers[0].steps[0].positions == (-1.5, 0.0)
    assert t_plan.controllers[1].step_names == ("home",)
    assert t_plan.controllers[1].steps[0].positions == (0.44, 0.0981)

    assert [controller.name for controller in v_plan.controllers] == [
        "arm_r_joint_trajectory_executor",
        "lift_joint_trajectory_executor",
    ]
    assert v_plan.controllers[0].step_names == ("home", "test1", "test2")
    assert v_plan.controllers[0].steps[1].positions == (0.0, -0.75)
    assert v_plan.controllers[1].step_names == ("home",)
    assert v_plan.controllers[1].steps[0].positions == (-0.15,)

    assert set(node._initial_pose_action_clients) == {
        "/arm_l_controller/follow_joint_trajectory",
        "/head_controller/follow_joint_trajectory",
        "/arm_r_controller/follow_joint_trajectory",
        "/lift_controller/follow_joint_trajectory",
    }
    assert set(node._latest_joint_states) == {"/joint_states"}
    shared_joint_state = FakeJointState(
        name=[
            "arm_l_joint1",
            "arm_l_joint2",
            "head_joint1",
            "head_joint2",
            "arm_r_joint1",
            "arm_r_joint2",
            "lift_joint",
        ],
        position=[0.0, 0.1, 0.2, 0.3, -0.1, -0.2, -0.3],
    )
    node._wait_for_joint_state = lambda joint_states_topic, timeout_sec=5.0: shared_joint_state
    node._handle_initial_pose_input("t")
    node._handle_initial_pose_input("v")

    send_entries = [entry for entry in node.call_log if entry[0] == "send"]
    assert send_entries[:2] == [
        ("send", "/arm_l_controller/follow_joint_trajectory", ("arm_l_joint1", "arm_l_joint2")),
        ("send", "/head_controller/follow_joint_trajectory", ("head_joint1", "head_joint2")),
    ]
    assert send_entries[2:] == [
        ("send", "/arm_r_controller/follow_joint_trajectory", ("arm_r_joint1", "arm_r_joint2")),
        ("send", "/lift_controller/follow_joint_trajectory", ("lift_joint",)),
        ("send", "/arm_r_controller/follow_joint_trajectory", ("arm_r_joint1", "arm_r_joint2")),
        ("send", "/arm_r_controller/follow_joint_trajectory", ("arm_r_joint1", "arm_r_joint2")),
    ]
