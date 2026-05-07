# rllab-inference ROS 2 packages

이 폴더는 Physical AI server에 inference command를 보내기 위한 ROS 2 패키지들을 포함합니다.

## Packages

- `physical_ai_interfaces`: Physical AI server와 통신하기 위한 msg/srv interface package
- `physical_ai_inference_client`: interactive inference controller
- `cam_head_resize_republisher`: camera image resize republisher

## Build

```bash
cd ~/ros2_ws/rllab-inference/ros2
source /opt/ros/jazzy/setup.bash
colcon build --packages-select physical_ai_interfaces physical_ai_inference_client
source install/setup.bash
```

## Run Inference Client

Physical AI server가 떠 있는 상태에서 실행합니다.

```bash
ros2 run physical_ai_inference_client start_inference
```

입력 흐름:

- `s`: robot type 선택 후 inference 시작
- `f`: inference 종료를 위해 `FINISH` command 전송
- `q`: client 종료

`s`를 누르면 client는 다음 순서로 service를 호출합니다.

```text
/get_robot_types
-> /set_robot_type
-> policy checkpoint path 직접 입력
-> /task/command START_INFERENCE
```

policy checkpoint path는 server가 접근할 수 있는 경로를 입력합니다. 예:

```text
/root/ros2_ws/src/physical_ai_tools/lerobot/outputs/train/dp_100000/pretrained_model
```

직접 path를 인자로 넣어서 한 번만 START_INFERENCE를 보낼 수도 있습니다.

```bash
ros2 run physical_ai_inference_client start_inference \
  /root/ros2_ws/src/physical_ai_tools/lerobot/outputs/train/dp_100000/pretrained_model
```

## Notes

현재 Physical AI server의 `/get_saved_policies` callback은 특정 HuggingFace cache 구조에서 server process를 죽일 수 있습니다. 그래서 client 기본 흐름에서는 `/get_saved_policies`를 호출하지 않고, checkpoint path를 직접 입력받습니다.

그래도 목록 조회를 강제로 사용하려면 다음 parameter를 켤 수 있습니다.

```bash
ros2 run physical_ai_inference_client start_inference \
  --ros-args -p use_saved_policy_list_service:=true
```

Inference 종료는 `STOP`이 아니라 `FINISH` command를 보냅니다. server 구현상 `STOP`은 `Recording stopped` 응답을 주지만 `on_inference`를 false로 만들지 않아 inference가 계속 돌 수 있습니다.
