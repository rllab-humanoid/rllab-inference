#!/usr/bin/env python3

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage


TOPIC_NAME = "/zed/zed_node/rgb/image_rect_color/compressed"
HOST = "0.0.0.0"
PORT = 8080


class SharedFrame:
    def __init__(self):
        self.condition = threading.Condition()
        self.jpeg_bytes = None
        self.frame_id = 0
        self.frame_count = 0
        self.last_format = ""
        self.last_size = 0
        self.last_time = 0.0

    def update(self, jpeg_bytes: bytes, msg_format: str):
        with self.condition:
            self.jpeg_bytes = jpeg_bytes
            self.frame_id += 1
            self.frame_count += 1
            self.last_format = msg_format
            self.last_size = len(jpeg_bytes)
            self.last_time = time.time()
            self.condition.notify_all()

    def get_status(self):
        with self.condition:
            age = None
            if self.last_time > 0:
                age = time.time() - self.last_time

            return {
                "frame_count": self.frame_count,
                "last_format": self.last_format,
                "last_size_bytes": self.last_size,
                "last_frame_age_sec": age,
            }


shared_frame = SharedFrame()


class ZedWebStreamer(Node):
    def __init__(self):
        super().__init__("zed_web_streamer_dgx")

        self.get_logger().info(f"Subscribing to {TOPIC_NAME}...")

        self.subscription = self.create_subscription(
            CompressedImage,
            TOPIC_NAME,
            self.image_callback,
            qos_profile_sensor_data,
        )

        self.timer = self.create_timer(2.0, self.status_timer)

    def status_timer(self):
        status = shared_frame.get_status()
        self.get_logger().info(
            f"Alive. Frames received: {status['frame_count']}, "
            f"last_size={status['last_size_bytes']}, "
            f"format={status['last_format']}"
        )

    def image_callback(self, msg: CompressedImage):
        # msg.data is already JPEG-compressed bytes.
        # Do NOT call cv2.imdecode() here.
        jpeg_bytes = bytes(msg.data)
        shared_frame.update(jpeg_bytes, msg.format)

        if shared_frame.frame_count == 1 or shared_frame.frame_count % 30 == 0:
            self.get_logger().info(
                f"Received frame {shared_frame.frame_count}, "
                f"format={msg.format}, bytes={len(jpeg_bytes)}"
            )


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep terminal clean. Comment this out if you want HTTP request logs.
        return

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self.send_index()
        elif self.path.startswith("/stream"):
            self.send_mjpeg_stream()
        elif self.path.startswith("/snapshot.jpg"):
            self.send_snapshot()
        elif self.path.startswith("/status"):
            self.send_status()
        else:
            self.send_error(404, "Not found")

    def send_index(self):
        html = f"""
<!doctype html>
<html>
<head>
  <title>ZED Web Stream</title>
  <style>
    body {{
      margin: 0;
      background: #111;
      color: #eee;
      font-family: Arial, sans-serif;
      text-align: center;
    }}
    h1 {{
      margin: 16px;
      font-size: 24px;
    }}
    img {{
      max-width: 95vw;
      max-height: 85vh;
      border: 2px solid #444;
      background: #000;
    }}
    .info {{
      margin: 12px;
      color: #aaa;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <h1>ZED Camera Stream</h1>
  <img src="/stream" />
  <div class="info">
    Topic: {TOPIC_NAME}<br>
    Snapshot: <a href="/snapshot.jpg" style="color:#8cf">/snapshot.jpg</a> |
    Status: <a href="/status" style="color:#8cf">/status</a>
  </div>
</body>
</html>
"""
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_status(self):
        data = json.dumps(shared_frame.get_status(), indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_snapshot(self):
        with shared_frame.condition:
            frame = shared_frame.jpeg_bytes

        if frame is None:
            self.send_error(503, "No frame received yet")
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.end_headers()
        self.wfile.write(frame)

    def send_mjpeg_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_frame_id = -1

        try:
            while True:
                with shared_frame.condition:
                    shared_frame.condition.wait_for(
                        lambda: shared_frame.jpeg_bytes is not None
                        and shared_frame.frame_id != last_frame_id,
                        timeout=5.0,
                    )

                    frame = shared_frame.jpeg_bytes
                    last_frame_id = shared_frame.frame_id

                if frame is None:
                    continue

                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            pass


def main(args=None):
    rclpy.init(args=args)
    node = ZedWebStreamer()

    ros_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    ros_thread.start()

    server = ThreadingHTTPServer((HOST, PORT), WebHandler)

    node.get_logger().info(f"Web stream running at: http://0.0.0.0:{PORT}")
    node.get_logger().info(f"From another machine, open: http://141.223.165.10:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()