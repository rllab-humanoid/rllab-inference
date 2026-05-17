# physical_ai_inference_client

`physical_ai_interfaces/srv/SendCommand` service에 `START_INFERENCE` request를 보내는 ROS 2 Python 패키지입니다.

## Dependency

이 패키지는 `physical_ai_interfaces`가 필요합니다. 아래 repository의 `physical_ai_interfaces` 패키지를 workspace에 받아서 같이 빌드해야 합니다.

https://github.com/ROBOTIS-GIT/physical_ai_tools/tree/main/physical_ai_interfaces

예시:

```bash
cd ~/ros2_ws/src
git clone https://github.com/ROBOTIS-GIT/physical_ai_tools.git
cd ~/ros2_ws
colcon build --packages-select physical_ai_interfaces physical_ai_inference_client
source install/setup.bash
```

## Run

실행하면 입력을 기다리는 interactive controller가 시작됩니다.

```bash
ros2 run physical_ai_inference_client start_inference
```

입력:

- `s`: robot type을 먼저 설정한 뒤 policy checkpoint path를 직접 입력받아 inference 시작
- `f`: `/task/command` service에 `FINISH` command 전송
- `t`: `initial_positions.yaml`에 기록된 초기 자세로 이동
- `q`: controller 종료

`s`를 누르면 먼저 `/get_robot_types`로 robot type 목록을 받아 선택하고, 선택한 값을 `/set_robot_type`에 설정한 뒤 policy checkpoint path를 직접 입력합니다. 현재 server의 `/get_saved_policies` callback은 특정 HuggingFace cache 구조에서 server process를 죽일 수 있어서 기본 흐름에서는 호출하지 않습니다.

inference를 시작하기 전에 `t`를 누르면 package config의 `initial_positions.yaml`을 읽어서 `step_names` 순서대로 초기 자세 trajectory를 보냅니다. 그 다음 `s`로 inference를 시작하면 됩니다.

그래도 `/get_saved_policies` 목록 조회를 쓰고 싶으면 명시적으로 켤 수 있습니다.

```bash
ros2 run physical_ai_inference_client start_inference \
  --ros-args -p use_saved_policy_list_service:=true
```

policy path를 직접 넘기면 기존처럼 한 번만 START_INFERENCE를 보냅니다.

```bash
ros2 run physical_ai_inference_client start_inference \
  /path/to/pretrained_model
```

train output root를 입력한 경우, client가 로컬에서 `checkpoints/*/pretrained_model` 후보를 찾을 수 있으면 실제 checkpoint를 고르게 합니다. 서버의 LeRobot loader는 보통 train root가 아니라 `pretrained_model` 폴더를 기대합니다.

기본 설정 파일을 사용하거나 service 이름 같은 ROS parameter를 바꾸고 싶으면 `--ros-args`를 사용합니다.

```bash
ros2 run physical_ai_inference_client start_inference \
  --ros-args --params-file ~/ros2_ws/src/physical_ai_inference_client/config/inference.yaml
```

policy path 직접 인자와 ROS parameter를 같이 쓸 수도 있습니다.

```bash
ros2 run physical_ai_inference_client start_inference \
  /path/to/pretrained_model \
  --ros-args -p service_name:=/task/command
```

## Test

실제 physical AI server 없이 request 형태를 확인하려면 테스트 service node를 먼저 실행합니다.

```bash
ros2 run physical_ai_inference_client test_send_command_server \
  --ros-args \
  -p expected_policy_path:=/path/to/pretrained_model
```

다른 터미널에서 client를 실행합니다.

```bash
ros2 run physical_ai_inference_client start_inference \
  /path/to/pretrained_model
```

테스트 service node가 `/get_saved_policies` 응답을 흉내 내고, 받은 `SendCommand` request의 `command`, `task_info.policy_path`, `fps`, `tags`, episode 설정 등을 로그로 출력합니다.

## Joint Slider GUI

각 관절 target을 slider로 확인하려면 다음 tool을 사용합니다.

```bash
ros2 run physical_ai_inference_client joint_slider_gui
```

이 GUI는 `/joint_states`를 subscribe해서 현재 관절값을 읽고, `FollowJointTrajectory` action goal을 아래 controller action namespace로 보냅니다. raw topic publish가 아니라 ROS 2 action goal입니다.

| controller | action namespace | joints |
| --- | --- | --- |
| left arm | `/arm_l_controller/follow_joint_trajectory` | `arm_l_joint1..7`, `gripper_l_joint1` |
| right arm | `/arm_r_controller/follow_joint_trajectory` | `arm_r_joint1..7`, `gripper_r_joint1` |
| head | `/head_controller/follow_joint_trajectory` | `head_joint1`, `head_joint2` |
| lift | `/lift_controller/follow_joint_trajectory` | `lift_joint` |

Slider range는 기본 `[-1.5, 1.5]` rad입니다. `Follow live /joint_states`가 기본으로 켜져 있어서 slider가 현재 관절값을 계속 따라갑니다. `Load Current /joint_states`를 누르면 즉시 현재 관절값으로 slider를 다시 채우고, `Send <controller>` 또는 `Send All`을 누르면 `trajectory_msgs/JointTrajectory`의 single point target을 해당 action server로 보냅니다. `Auto send controller on slider release`를 켜면 slider를 놓을 때 해당 controller만 전송합니다.

필요하면 ROS parameter로 range/action name/duration을 바꿀 수 있습니다.

```bash
ros2 run physical_ai_inference_client joint_slider_gui --ros-args \
  -p min_position:=-1.5 \
  -p max_position:=1.5 \
  -p trajectory_duration_s:=1.0 \
  -p joint_states_topic:=/joint_states
```

## Record And Use Initial Pose

초기 자세를 만들고 실제 client에서 쓰는 흐름은 다음과 같습니다.

1. slider GUI로 원하는 자세를 만듭니다.

```bash
ros2 run physical_ai_inference_client joint_slider_gui
```

2. 다른 터미널에서 현재 `/joint_states`를 기록합니다.

```bash
ros2 run physical_ai_inference_client record_joint_positions
```

원하는 자세가 되었을 때 Enter를 누르고 step name을 입력하면 `~/joint_recordings/<step_name>_<timestamp>.yaml`에 저장됩니다. 종료할 때 출력되는 `initial_positions.yaml 붙여넣기용 블록`을 복사해서 아래 파일에 넣습니다.

```text
ros2/physical_ai_inference_client/config/initial_positions.yaml
```

예시는 다음 형태입니다.

```yaml
duration: 5.0
trajectory_timeout_s: 30.0

step_names:
  - extend_sideways
  - final_pose

extend_sideways:
  arm_l_positions: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0]
  arm_r_positions: [-0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7, 0.0]
  head_positions: [0.0, 0.2]

final_pose:
  arm_l_positions: [0.2, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0]
  arm_r_positions: [-0.2, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7, 0.0]
  head_positions: [0.0, 0.1]
  lift_positions: [0.0]
```

특정 joint를 현재 값 그대로 두고 싶으면 해당 위치에 `null`을 넣습니다. 예를 들어 `arm_l_positions: [null, null, 0.5, null, null, null, null, null]`은 `arm_l_joint3`만 `0.5`로 보내고 나머지는 현재 `/joint_states` 값을 유지합니다.

3. config를 수정한 뒤 workspace를 다시 build/source합니다.

```bash
cd /scratch/e1816a03/rllab-inference/ros2
colcon build --packages-select physical_ai_interfaces physical_ai_inference_client
source install/setup.bash
```

`start_inference`는 package share에 설치된 config를 읽습니다. source tree의 `config/initial_positions.yaml`만 고치고 다시 build/source하지 않으면 이전 install config가 사용될 수 있습니다.

4. 실제 client에서 초기 자세를 사용합니다.

```bash
ros2 run physical_ai_inference_client start_inference
```

interactive prompt에서:

```text
t  # initial_positions.yaml의 step_names 순서대로 초기 자세 이동
s  # robot type 선택 후 policy path 입력, START_INFERENCE 전송
f  # inference 종료를 위해 FINISH 전송
q  # client 종료
```

초기 자세 이동도 slider GUI와 동일하게 `FollowJointTrajectory` action goal을 `/arm_l_controller/follow_joint_trajectory`, `/arm_r_controller/follow_joint_trajectory`, `/head_controller/follow_joint_trajectory`, `/lift_controller/follow_joint_trajectory`로 보냅니다.
