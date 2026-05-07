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
- `q`: controller 종료

`s`를 누르면 먼저 `/get_robot_types`로 robot type 목록을 받아 선택하고, 선택한 값을 `/set_robot_type`에 설정한 뒤 policy checkpoint path를 직접 입력합니다. 현재 server의 `/get_saved_policies` callback은 특정 HuggingFace cache 구조에서 server process를 죽일 수 있어서 기본 흐름에서는 호출하지 않습니다.

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
