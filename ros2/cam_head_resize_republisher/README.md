# Cam Head Resize Republisher

This package launches a ROS2 node that subscribes to the compressed `cam_head` (ZED) image topic provided by ROBOTIS `ai_worker`, resizes the image to match the wrist camera resolution, and republishes it as a new topic.

### Purpose
Diffusion Policy (DP) training requires all input images to have the same resolution. However, the current camera streams use different resolutions. For real-time inference, the cam_head image is resized to match the wrist camera resolution.

## 00. Build
```bash
cd ~/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash

python3 -m colcon build --packages-select cam_head_resize_republisher
source install/setup.bash
```

## 01. Run
Run the following command on the remote computer:
```bash
ros2 run cam_head_resize_republisher cam_head_resize_republish
```

## 02. Application
When using the ROBOTIS `ai_worker` inference pipeline, the robot subscribes to topics defined in a YAML configuration file through the [SetRobotType](https://github.com/ROBOTIS-GIT/physical_ai_tools/blob/f2f74cef6639defab4064b1f12ef129ab63e487d/physical_ai_interfaces/srv/SetRobotType.srv) service.

[Example configuration](https://github.com/ROBOTIS-GIT/physical_ai_tools/tree/main/physical_ai_server/config):
```
physical_ai_server:
  ros__parameters:
    ffw_bg2_rev4:
      observation_list:
        - cam_head
        - cam_wrist_left
        - cam_wrist_right
        - state

      camera_topic_list: 
        - cam_head:/zed/zed_node/left/image_rect_color/compressed
        - cam_wrist_left:/camera_left/camera_left/color/image_rect_raw/compressed
        - cam_wrist_right:/camera_right/camera_right/color/image_rect_raw/compressed

      joint_topic_list:
         ...
```

To use the resized camera stream, override the cam_head topic with the republished topic and create new yaml:
```
camera_topic_list: 
  - cam_head:/zed/zed_node/left/image_rect_color_resized/compressed                  # CHANGED!
  - cam_wrist_left:/camera_left/camera_left/color/image_rect_raw/compressed
  - cam_wrist_right:/camera_right/camera_right/color/image_rect_raw/compressed
```
