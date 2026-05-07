#!/usr/bin/env python3
from typing import Optional

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage


class CamHeadResizeRepublisher(Node):
    """Subscribe to compressed cam_head image, resize, and republish compressed."""

    DEFAULT_INPUT_TOPIC = '/zed/zed_node/left/image_rect_color/compressed'
    DEFAULT_OUTPUT_TOPIC = '/zed/zed_node/left/image_rect_color_resized/compressed'
    DEFAULT_WIDTH = 424
    DEFAULT_HEIGHT = 240
    DEFAULT_JPEG_QUALITY = 95

    def __init__(self) -> None:
        super().__init__('cam_head_resize_republisher')

        self.declare_parameter('input_topic', self.DEFAULT_INPUT_TOPIC)
        self.declare_parameter('output_topic', self.DEFAULT_OUTPUT_TOPIC)
        self.declare_parameter('target_width', self.DEFAULT_WIDTH)
        self.declare_parameter('target_height', self.DEFAULT_HEIGHT)
        self.declare_parameter('jpeg_quality', self.DEFAULT_JPEG_QUALITY)

        self.input_topic = self.get_parameter('input_topic').get_parameter_value().string_value
        self.output_topic = self.get_parameter('output_topic').get_parameter_value().string_value
        self.target_width = self.get_parameter('target_width').get_parameter_value().integer_value
        self.target_height = self.get_parameter('target_height').get_parameter_value().integer_value
        self.jpeg_quality = self.get_parameter('jpeg_quality').get_parameter_value().integer_value

        self._bridge = CvBridge()
        self._publisher = self.create_publisher(CompressedImage, self.output_topic, 10)
        self._subscriber = self.create_subscription(
            CompressedImage,
            self.input_topic,
            self._image_callback,
            10,
        )

        self.get_logger().info(
            'Cam head resize republisher started: '
            f'{self.input_topic} -> {self.output_topic} '
            f'({self.target_width}x{self.target_height})'
        )

    def _image_callback(self, msg: CompressedImage) -> None:
        try:
            cv_image = self._bridge.compressed_imgmsg_to_cv2(msg, desired_encoding='bgr8')
            resized_image = cv2.resize(
                cv_image,
                (int(self.target_width), int(self.target_height)),
                interpolation=cv2.INTER_AREA,
            )

            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)]
            success, encoded = cv2.imencode('.jpg', resized_image, encode_params)
            if not success:
                self.get_logger().error('Failed to encode resized image to JPEG')
                return

            out_msg = CompressedImage()
            out_msg.header = msg.header
            out_msg.format = 'bgra8; jpeg compressed brg8'
            out_msg.data = encoded.tobytes()
            self._publisher.publish(out_msg)

        except Exception as exc:
            self.get_logger().error(f'Failed to resize and republish image: {exc}')


def main(args: Optional[list] = None) -> None:
    rclpy.init(args=args)
    node = CamHeadResizeRepublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()