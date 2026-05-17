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


class FakeNode:
    def __init__(self, name):
        self.name = name
        self.parameters = {}
        self.subscriptions = []
        self.logger = FakeLogger()

    def declare_parameter(self, name, default_value):
        self.parameters[name] = default_value

    def get_parameter(self, name):
        return FakeParameter(self.parameters[name])

    def create_subscription(self, msg_type, topic, callback, qos):
        self.subscriptions.append((msg_type, topic, callback, qos))
        return callback

    def get_logger(self):
        return self.logger

    def destroy_node(self):
        pass


class FakeActionFuture:
    def __init__(self):
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)

    def result(self):
        return types.SimpleNamespace(accepted=True)


class FakeActionClient:
    instances = []

    def __init__(self, node, action_type, action_name):
        self.node = node
        self.action_type = action_type
        self.action_name = action_name
        self.sent_goals = []
        self.server_available = True
        FakeActionClient.instances.append(self)

    def wait_for_server(self, timeout_sec):
        self.wait_timeout = timeout_sec
        return self.server_available

    def send_goal_async(self, goal):
        self.sent_goals.append(goal)
        return FakeActionFuture()


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
        self.time_from_start = types.SimpleNamespace(sec=0, nanosec=0)


class FakeFollowJointTrajectory:
    class Goal:
        def __init__(self):
            self.trajectory = None


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, *, text):
        self.text = text


def install_ros_stubs():
    rclpy = types.ModuleType("rclpy")
    rclpy.init = lambda args=None: None
    rclpy.ok = lambda: True
    rclpy.shutdown = lambda: None
    rclpy.spin = lambda node: None

    rclpy_node = types.ModuleType("rclpy.node")
    rclpy_node.Node = FakeNode
    rclpy.node = rclpy_node

    rclpy_action = types.ModuleType("rclpy.action")
    rclpy_action.ActionClient = FakeActionClient
    rclpy.action = rclpy_action

    control_msgs = types.ModuleType("control_msgs")
    control_msgs_action = types.ModuleType("control_msgs.action")
    control_msgs_action.FollowJointTrajectory = FakeFollowJointTrajectory
    control_msgs.action = control_msgs_action

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
        "control_msgs": control_msgs,
        "control_msgs.action": control_msgs_action,
        "sensor_msgs": sensor_msgs,
        "sensor_msgs.msg": sensor_msgs_msg,
        "trajectory_msgs": trajectory_msgs,
        "trajectory_msgs.msg": trajectory_msgs_msg,
    }
    sys.modules.update(modules)


def import_joint_slider_gui():
    install_ros_stubs()
    package_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(package_root))
    sys.modules.pop("physical_ai_inference_client.joint_slider_gui", None)
    return importlib.import_module("physical_ai_inference_client.joint_slider_gui")


def test_node_reads_joint_states_and_sends_follow_joint_trajectory_goal():
    module = import_joint_slider_gui()
    FakeActionClient.instances.clear()
    node = module.JointSliderNode()
    node._joint_state_callback(
        FakeJointState(
            name=["arm_l_joint1", "arm_l_joint2", "lift_joint"],
            position=[0.25, -0.5, 1.25],
        )
    )

    assert node.latest_positions() == {
        "arm_l_joint1": 0.25,
        "arm_l_joint2": -0.5,
        "lift_joint": 1.25,
    }

    spec = node.controllers[0]
    positions = [0.1 * index for index in range(len(spec.joint_names))]
    message = node.send_controller(spec, positions)

    client = node.action_clients["arm_l"]
    assert message == "arm_l: sent 8 joint targets"
    assert client.action_name == "/arm_l_controller/follow_joint_trajectory"
    assert len(client.sent_goals) == 1
    goal = client.sent_goals[0]
    assert goal.trajectory.joint_names == list(spec.joint_names)
    assert goal.trajectory.points[0].positions == positions
    assert goal.trajectory.points[0].time_from_start.sec == 1
    assert goal.trajectory.points[0].time_from_start.nanosec == 0


def test_gui_live_joint_state_update_clamps_and_skips_dragged_joint():
    module = import_joint_slider_gui()
    gui = object.__new__(module.JointSliderGui)
    gui.node = types.SimpleNamespace(min_position=-1.5, max_position=1.5)
    gui.slider_vars = {
        "arm_l_joint1": FakeVar(0.0),
        "arm_l_joint2": FakeVar(0.0),
    }
    gui.value_labels = {
        "arm_l_joint1": FakeLabel(),
        "arm_l_joint2": FakeLabel(),
    }
    gui.dragging_joints = {"arm_l_joint2"}

    loaded = module.JointSliderGui._apply_joint_state_positions(
        gui,
        {"arm_l_joint1": 2.0, "arm_l_joint2": 0.75},
        skip_dragging=True,
    )

    assert loaded == 1
    assert gui.slider_vars["arm_l_joint1"].get() == 1.5
    assert gui.value_labels["arm_l_joint1"].text == "1.500"
    assert gui.slider_vars["arm_l_joint2"].get() == 0.0

    loaded = module.JointSliderGui._apply_joint_state_positions(
        gui,
        {"arm_l_joint1": -2.0, "arm_l_joint2": 0.75},
        skip_dragging=False,
    )

    assert loaded == 2
    assert gui.slider_vars["arm_l_joint1"].get() == -1.5
    assert gui.slider_vars["arm_l_joint2"].get() == 0.75
    assert gui.value_labels["arm_l_joint2"].text == "0.750"


def test_slider_release_reenables_live_follow_and_optionally_sends_controller():
    module = import_joint_slider_gui()
    gui = object.__new__(module.JointSliderGui)
    gui.dragging_joints = {"arm_l_joint1"}
    gui.auto_send_var = FakeVar(True)
    sent = []
    gui.send_controller = sent.append

    module.JointSliderGui._on_slider_release(gui, "arm_l", "arm_l_joint1")

    assert "arm_l_joint1" not in gui.dragging_joints
    assert sent == ["arm_l"]
