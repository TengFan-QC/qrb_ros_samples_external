# Copyright (c) 2025 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Clear

import rclpy
import cv2
import math
import numpy as np
import time
import threading
import signal
import sys

from collections import deque
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from qrb_ros_tensor_list_msgs.msg import Tensor, TensorList
from rclpy.signals import SignalHandlerOptions


class DepthEstimationNode(Node):
    def __init__(self):
        super().__init__('qrb_ros_depth_estimator')

        # Separate callback groups so the (CPU-bound) preprocessing path and the
        # postprocessing path can run concurrently on the MultiThreadedExecutor.
        # Without this, rclpy puts every callback of a node into one mutually
        # exclusive group, which would serialize image_callback and
        # infer_callback and defeat the pipelining below.
        self.input_cb_group = MutuallyExclusiveCallbackGroup()
        self.output_cb_group = MutuallyExclusiveCallbackGroup()

        self.publisher_ = self.create_publisher(Image, 'depth_map', 10)
        self.bridge = CvBridge()

        self.get_logger().info("Use qnn inference node!")
        self.image_listener_ = self.create_subscription(
            Image, self.get_namespace() + '/cam0_stream1', self.image_callback, 30,
            callback_group=self.input_cb_group)
        self.camera_listener_ = self.create_subscription(
            Image, '/image_raw', self.image_callback, 30,
            callback_group=self.input_cb_group)

        self.qnn_infer_subscriber = self.create_subscription(
            TensorList,
            'qrb_inference_output_tensor',  # subscriber qnn infer output topic
            self.infer_callback,
            30,
            callback_group=self.output_cb_group
        )
        self.qnn_infer_publisher = self.create_publisher(
            TensorList,
            'qrb_inference_input_tensor',  # publish qnn infer input topic
            30
        )
        # Input tensor size
        self.target_size = [518, 518]

        # ---- Pipelining ----
        # Allow a few frames to be "in flight" (preprocessed + published to QNN
        # but not yet returned) so the preprocessing of the next frame overlaps
        # the inference of the current one. Previously only a single frame was
        # ever in flight (the msg_count 0/1 gate), which serialized the whole
        # pipeline and capped throughput at 1 / (pre + infer + post).
        self.max_in_flight = 3
        self.in_flight = 0
        # Per-frame metadata travels alongside the frame instead of living in
        # shared instance variables (which would race once >1 frame is in
        # flight). QNN preserves order and the output topic has a single
        # publisher, so a FIFO queue reliably matches each result to its frame.
        self.meta_queue = deque()
        self.pipeline_lock = threading.Lock()

        # KeyboardInterrupt exception handle
        self.stopping = False

    def nv12_to_bgr(self, nv12_image, width, height):
        """
        Convert NV12 image to BGR format.
        """
        yuv = nv12_image.reshape((height * 3 // 2, width))
        bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV12)
        return bgr

    def image_callback(self, msg):
        # Check if we're shutting down
        if self.stopping:
            return

        # Backpressure: only let a bounded number of frames be in flight so the
        # next frame's preprocessing overlaps the current frame's inference,
        # without unboundedly queuing work faster than QNN can drain it.
        with self.pipeline_lock:
            if self.in_flight >= self.max_in_flight:
                return
        start = time.perf_counter()
        if msg.encoding == 'nv12':
            nv12_data = np.frombuffer(msg.data, dtype=np.uint8)
            image = self.nv12_to_bgr(nv12_data, msg.width, msg.height)
        elif msg.encoding == 'bgr8':
            image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        else:
            self.get_logger().error(f'Unsupported image encoding: {msg.encoding}')
            return

        if image.shape[-1] != 3:
           raise ValueError("Need input 3 channels image")
        try:
            input, origin_wh, scale, padding = self.preprocess(image)
            out_msg = TensorList()
            tensor = Tensor()
            tensor.data_type = 2
            tensor.name = "depth_anything_input_tensor"
            tensor.shape = [1, 518, 518, 3]
            tensor.data = input.tobytes()
            out_msg.tensor_list.append(tensor)

            # Enqueue this frame's metadata and publish atomically so the FIFO
            # order of meta_queue matches the publish order (and therefore the
            # order QNN returns results in). image_callback runs in a mutually
            # exclusive group, so these never interleave with each other.
            with self.pipeline_lock:
                if self.stopping:
                    return
                self.meta_queue.append((origin_wh, scale, padding))
                try:
                    self.qnn_infer_publisher.publish(out_msg)
                    self.in_flight += 1
                except Exception:
                    # Context may be invalid during shutdown; roll back the
                    # metadata we just enqueued so it can't desync the FIFO.
                    self.meta_queue.pop()
                    return
            latency_ms = (time.perf_counter() - start) * 1000
            self.get_logger().info(f'Published qnn input tensor, pre process: {latency_ms:.2f} ms')
        except Exception as e:
            self.get_logger().error(f'Error preprocessing image: {e}')
        
    def infer_callback(self, msg):
        try:
            start = time.perf_counter()

            if self.stopping:
                with self.pipeline_lock:
                    if self.meta_queue:
                        self.meta_queue.popleft()
                    if self.in_flight > 0:
                        self.in_flight -= 1
                return

            # Match this result to the frame that produced it (FIFO order).
            with self.pipeline_lock:
                if not self.meta_queue:
                    self.get_logger().warn('Inference result with no pending frame metadata; dropping')
                    if self.in_flight > 0:
                        self.in_flight -= 1
                    return
                origin_wh, scale, padding = self.meta_queue.popleft()
                if self.in_flight > 0:
                    self.in_flight -= 1

            for result_tensor in msg.tensor_list:  # iterate tensor_list
                output_data = np.array(result_tensor.data)
                depth_map = output_data.view(np.float32)
                depth_color_map = self.postprocess(depth_map, origin_wh, scale, padding)
                out_msg = self.bridge.cv2_to_imgmsg(depth_color_map, encoding='bgr8')
                self.publisher_.publish(out_msg)
                latency_ms = (time.perf_counter() - start) * 1000
                self.get_logger().info(f'Published depth map, post process: {latency_ms:.2f} ms')
        except Exception as e:
            if not self.stopping:
                self.get_logger().error(f'Error processing image: {e}')

    def preprocess(self, image):
        """
        Resize and pad image to be shape [..., dst_size[0], dst_size[1]]

        Parameters:
            image: (H, W, ...)
                Image to reshape.

        Returns:
            rescaled_padded_image: cv2.Image (..., dst_size[0], dst_size[1])
            scale: scale factor between original image and dst_size image, (w, h)
            pad: pixels of padding added to the rescaled image: (left_padding, top_padding)

        Based on https://github.com/zmurez/MediaPipePyTorch/blob/master/blazebase.py
        """
        height, width = image.shape[0:2]
        dst_frame_height, dst_frame_width = self.target_size[1], self.target_size[0]

        h_ratio = dst_frame_height / height
        w_ratio = dst_frame_width / width
        scale = min(h_ratio, w_ratio)
        if h_ratio < w_ratio:
            scale = h_ratio
            new_height = dst_frame_height
            new_width = math.floor(width * scale)
        else:
            scale = w_ratio
            new_height = math.floor(height * scale)
            new_width = dst_frame_width

        new_height = math.floor(height * scale)
        new_width = math.floor(width * scale)
        pad_h = dst_frame_height - new_height
        pad_w = dst_frame_width - new_width

        pad_top = int(pad_h // 2)
        pad_bottom = int(pad_h // 2 + pad_h % 2)
        pad_left = int(pad_w // 2)
        pad_right = int(pad_w // 2 + pad_w % 2)

        rescaled_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_CUBIC)

        rescaled_padded_image = cv2.copyMakeBorder(rescaled_image, pad_top, pad_bottom, pad_left, pad_right, 
                                cv2.BORDER_CONSTANT, value=(0,0,0))
        padding = (pad_left, pad_top)
        normalized = rescaled_padded_image.astype(np.float32) / 255.0
        return normalized[np.newaxis, ...], (width, height), scale, padding

    def postprocess(self, 
                    depth_map, 
                    origin_wh: tuple[int, int], 
                    scale: float, 
                    padding: tuple[int, int]
                    ):
        """Resize and undo padding on the depth map, then cenvert it to color map.

        Args:
            origin_wh (tuple[int, int]): origin image size
            scale (float): resize scale
            padding (tuple[int, int]): padding params(left, top)

        Returns:
            _type_: color map image
        """
        depth_map = depth_map.reshape((self.target_size[0], self.target_size[1], 1)) #Reshape to [518, 518, 1]

        output_image = self.undo_resize_pad(depth_map, origin_wh, scale, padding)
        # Normalize to [0,255]
        normalized = cv2.normalize(output_image, None, 0, 255, cv2.NORM_MINMAX)
        colored = cv2.applyColorMap(normalized.astype(np.uint8), cv2.COLORMAP_INFERNO)
        return colored

    def undo_resize_pad(self,
            image: np.ndarray,
            orig_size_wh: tuple[int, int],
            scale: float,
            padding: tuple[int, int],
        ) -> np.ndarray:
        """
        Undoes the effect of resize_pad. Instead of scale, the original size
        (in order width, height) is provided to prevent an off-by-one size.
        """
        width, height = orig_size_wh
        # Rescale the image using OpenCV
        rescaled_image_np = cv2.resize(image, None, fx=1/scale, fy=1/scale, interpolation=cv2.INTER_LINEAR)
        # Calculate the scaled padding
        scaled_padding = [int(round(padding[0] / scale)), int(round(padding[1] / scale))]
        # Crop the image
        cropped_image_np = rescaled_image_np[
            scaled_padding[1] : scaled_padding[1] + height,
            scaled_padding[0] : scaled_padding[0] + width
        ]

        return cropped_image_np
    

def main(args=None):
    # Initialize with signal handler options for ROS2 Jazzy
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    
    node = None
    executor = None
    shutdown_requested = threading.Event()
    
    def signal_handler(signum, frame):
        """Custom signal handler for graceful shutdown"""
        print(f"\nReceived signal {signum}, initiating graceful shutdown...")
        shutdown_requested.set()
    
    # Register custom signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        node = DepthEstimationNode()
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        
        # Spin in a way that allows checking for shutdown
        while rclpy.ok() and not shutdown_requested.is_set():
            executor.spin_once(timeout_sec=0.1)
            
    except Exception as e:
        print(f"Exception during execution: {e}")
    finally:
        print("Starting cleanup sequence...")
        
        if node:
            # Signal that we're stopping - this prevents new inference requests
            node.stopping = True
            
            # Wait for any in-flight inference to complete
            max_wait_time = 3.0  # Maximum wait time in seconds
            wait_interval = 0.1  # Check interval in seconds
            elapsed = 0.0
            
            print("Waiting for in-flight inference to complete...")

            while elapsed < max_wait_time:
                with node.pipeline_lock:
                    if node.in_flight == 0:
                        break
                time.sleep(wait_interval)
                elapsed += wait_interval
            
            if elapsed >= max_wait_time:
                print("Warning: Inference did not complete within timeout")
            else:
                print("In-flight inference completed successfully")
            
            # Critical: Give QNN node time to finish processing
            # This prevents QNN errors during shutdown
            print("Allowing QNN node to complete cleanup...")
            time.sleep(1.5)
        
        # Shutdown executor first to stop message processing
        if executor:
            try:
                print("Shutting down executor...")
                executor.shutdown(timeout_sec=2.0)
            except Exception:
                pass  # Suppress errors during shutdown
        
        # Destroy the node
        if node:
            try:
                node.destroy_node()
            except Exception:
                pass  # Suppress errors during shutdown
        
        # Finally shutdown rclpy
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except Exception:
                pass  # Suppress errors during shutdown
        
        print("Shutdown complete")
        sys.exit(0)


if __name__ == '__main__':
    main()
