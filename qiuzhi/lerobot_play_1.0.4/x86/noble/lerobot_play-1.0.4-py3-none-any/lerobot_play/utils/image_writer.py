#!/usr/bin/env python

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import multiprocessing
import queue
import threading
from pathlib import Path

import numpy as np
import PIL.Image
import torch
from mcap.writer import Writer
from mcap.reader import make_reader
from io import BytesIO
import os


def safe_stop_image_writer(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            dataset = kwargs.get("dataset")
            image_writer = getattr(dataset, "image_writer", None) if dataset else None
            if image_writer is not None:
                print("Waiting for image writer to terminate...")
                image_writer.stop()
            raise e

    return wrapper


def image_array_to_pil_image(
    image_array: np.ndarray, range_check: bool = True
) -> PIL.Image.Image:
    # TODO(aliberts): handle 1 channel and 4 for depth images
    if image_array.ndim != 3:
        raise ValueError(
            f"The array has {image_array.ndim} dimensions, but 3 is expected for an image."
        )

    if image_array.shape[0] == 3:
        # Transpose from pytorch convention (C, H, W) to (H, W, C)
        image_array = image_array.transpose(1, 2, 0)

    elif image_array.shape[-1] != 3:
        raise NotImplementedError(
            f"The image has {image_array.shape[-1]} channels, but 3 is required for now."
        )

    if image_array.dtype != np.uint8:
        if range_check:
            max_ = image_array.max().item()
            min_ = image_array.min().item()
            if max_ > 1.0 or min_ < 0.0:
                raise ValueError(
                    "The image data type is float, which requires values in the range [0.0, 1.0]. "
                    f"However, the provided range is [{min_}, {max_}]. Please adjust the range or "
                    "provide a uint8 image with values in the range [0, 255]."
                )

        image_array = (image_array * 255).astype(np.uint8)

    return PIL.Image.fromarray(image_array)


def append_image_to_mcap(
    image: PIL.Image.Image,
    mcap_file: Path,
    topic_name: str = "mcap",
    frame_index: int = 0,
):
    # print(f"=== 调试信息 ===")
    # print(f"文件路径: {mcap_file}")
    # print(f"frame_index 值: {frame_index}")
    # print(f"frame_index 类型: {type(frame_index)}")
    # 转换为Path对象
    file_path = Path(mcap_file) if isinstance(mcap_file, str) else mcap_file

    # 确保目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 编码图像
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format="PNG")
    image_data = img_byte_arr.getvalue()

    # 关键修复：处理追加模式
    if file_path.exists():
        # 方法1：读取现有文件，添加新帧，重新写入（推荐）
        return _append_by_recreating(image_data, file_path, topic_name, frame_index)
    else:
        # 创建新文件
        with file_path.open("wb") as f:
            writer = Writer(f)
            writer.start()

            channel_id = writer.register_channel(
                topic=topic_name, message_encoding="image/png", schema_id=0  # 改为None
            )

            writer.add_message(
                channel_id=channel_id,
                log_time=frame_index,
                data=image_data,
                publish_time=frame_index,
            )

            writer.finish()


def _append_by_recreating(image_data, file_path, topic_name, frame_index):
    """
    通过重新创建文件来追加数据（最可靠的方法）
    """
    from mcap.reader import make_reader
    import tempfile
    import shutil

    print("使用重新创建方式追加...")

    # 收集现有消息
    existing_messages = []

    try:
        with file_path.open("rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                existing_messages.append(
                    {
                        "topic": channel.topic,
                        "encoding": channel.message_encoding,
                        "schema_id": channel.schema_id,
                        "log_time": message.log_time,
                        "data": message.data,
                    }
                )
    except Exception as e:
        print(f"读取现有文件失败: {e}")
        return None

    print(f"读取到 {len(existing_messages)} 条现有消息")

    # 添加新消息
    existing_messages.append(
        {
            "topic": topic_name,
            "encoding": "image/png",
            "schema_id": 0,
            "log_time": frame_index,
            "data": image_data,
        }
    )

    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mcap") as tmp:
        writer = Writer(tmp)
        writer.start()

        # 注册通道（使用第一个消息的配置）
        first_msg = existing_messages[0]
        channel_id = writer.register_channel(
            topic=first_msg["topic"],
            message_encoding=first_msg["encoding"],
            schema_id=first_msg["schema_id"],
        )

        # 按时间戳排序并写入所有消息
        for msg in sorted(existing_messages, key=lambda x: x["log_time"]):
            writer.add_message(
                channel_id=channel_id,
                log_time=msg["log_time"],
                data=msg["data"],
                publish_time=msg["log_time"],
            )

        writer.finish()
        tmp_path = Path(tmp.name)

    # 替换原文件
    shutil.move(str(tmp_path), str(file_path))
    print(f"追加完成，总消息数: {len(existing_messages)}")

    return frame_index


def write_image(
    image: np.ndarray | PIL.Image.Image, fpath: Path, compress_level: int = 1
):
    """
    Saves a NumPy array or PIL Image to a file.

    This function handles both NumPy arrays and PIL Image objects, converting
    the former to a PIL Image before saving. It includes error handling for
    the save operation.

    Args:
        image (np.ndarray | PIL.Image.Image): The image data to save.
        fpath (Path): The destination file path for the image.
        compress_level (int, optional): The compression level for the saved
            image, as used by PIL.Image.save(). Defaults to 1.
            Refer to: https://github.com/huggingface/lerobot/pull/2135
            for more details on the default value rationale.

    Raises:
        TypeError: If the input 'image' is not a NumPy array or a
            PIL.Image.Image object.

    Side Effects:
        Prints an error message to the console if the image writing process
        fails for any reason.
    """
    try:
        if isinstance(image, np.ndarray):
            img = image_array_to_pil_image(image)
        elif isinstance(image, PIL.Image.Image):
            img = image
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")
        img.save(fpath, compress_level=compress_level)
    except Exception as e:
        print(f"Error writing image {fpath}: {e}")


def write_mcap(image: np.ndarray | PIL.Image.Image, fpath: Path, frame_index: int = 0):
    try:
        if isinstance(image, np.ndarray):
            img = image_array_to_pil_image(image)
        elif isinstance(image, PIL.Image.Image):
            img = image
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")
        append_image_to_mcap(img, fpath, frame_index=frame_index)
    except Exception as e:
        print(f"Error writing image {fpath}: {e}")


def worker_thread_loop(queue: queue.Queue):
    while True:
        item = queue.get()
        if item is None:
            queue.task_done()
            break
        image_array, fpath, compress_level = item
        write_image(image_array, fpath, compress_level)
        queue.task_done()


def worker_process(queue: queue.Queue, num_threads: int):
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker_thread_loop, args=(queue,))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


class AsyncImageWriter:
    """
    This class abstract away the initialisation of processes or/and threads to
    save images on disk asynchronously, which is critical to control a robot and record data
    at a high frame rate.

    When `num_processes=0`, it creates a threads pool of size `num_threads`.
    When `num_processes>0`, it creates processes pool of size `num_processes`, where each subprocess starts
    their own threads pool of size `num_threads`.

    The optimal number of processes and threads depends on your computer capabilities.
    We advise to use 4 threads per camera with 0 processes. If the fps is not stable, try to increase or lower
    the number of threads. If it is still not stable, try to use 1 subprocess, or more.
    """

    def __init__(self, num_processes: int = 0, num_threads: int = 1):
        self.num_processes = num_processes
        self.num_threads = num_threads
        self.queue = None
        self.threads = []
        self.processes = []
        self._stopped = False

        if num_threads <= 0 and num_processes <= 0:
            raise ValueError(
                "Number of threads and processes must be greater than zero."
            )

        if self.num_processes == 0:
            # Use threading
            self.queue = queue.Queue()
            for _ in range(self.num_threads):
                t = threading.Thread(target=worker_thread_loop, args=(self.queue,))
                t.daemon = True
                t.start()
                self.threads.append(t)
        else:
            # Use multiprocessing
            self.queue = multiprocessing.JoinableQueue()
            for _ in range(self.num_processes):
                p = multiprocessing.Process(
                    target=worker_process, args=(self.queue, self.num_threads)
                )
                p.daemon = True
                p.start()
                self.processes.append(p)

    def save_image(
        self,
        image: torch.Tensor | np.ndarray | PIL.Image.Image,
        fpath: Path,
        compress_level: int = 1,
    ):
        if isinstance(image, torch.Tensor):
            # Convert tensor to numpy array to minimize main process time
            image = image.cpu().numpy()
        self.queue.put((image, fpath, compress_level))

    def wait_until_done(self):
        self.queue.join()

    def stop(self):
        if self._stopped:
            return

        if self.num_processes == 0:
            for _ in self.threads:
                self.queue.put(None)
            for t in self.threads:
                t.join()
        else:
            num_nones = self.num_processes * self.num_threads
            for _ in range(num_nones):
                self.queue.put(None)
            for p in self.processes:
                p.join()
                if p.is_alive():
                    p.terminate()
            self.queue.close()
            self.queue.join_thread()

        self._stopped = True
