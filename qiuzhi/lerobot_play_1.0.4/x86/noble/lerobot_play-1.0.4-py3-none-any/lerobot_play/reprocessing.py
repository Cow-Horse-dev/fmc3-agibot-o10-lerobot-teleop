import argparse
from pathlib import Path
import json
import io
import cv2
import numpy as np
from mcap.reader import make_reader
from PIL import Image
import time
import subprocess
import sys
import tempfile
import shutil
import pandas as pd
import av
import math
import os

class McapToMp4Converter:
    """MCAP转MP4转换器"""

    def __init__(self, fps=30, crf=34, cpu_used=6):
        """
        初始化转换器

        Args:
            fps: 视频帧率
            crf: AV1 CRF质量参数 (0-63，越小质量越好)
            cpu_used: AV1编码速度 (0-8，越小质量越好但越慢)
        """
        self.fps = fps
        self.crf = crf
        self.cpu_used = cpu_used
        self.stats = {
            'total_frames': 0,
            'processed_frames': 0,
            'width': 0,
            'height': 0,
            'decode_time': 0,
            'encode_time': 0,
            'total_time': 0
        }

    def check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except:
            print("错误: 未找到ffmpeg")
            return False

    # def extract_frames(self, input_file, temp_dir):
    #     """提取MCAP中的图像帧"""
    #     frames = []
    #     frame_count = 0

    #     with open(input_file, "rb") as f:
    #         reader = make_reader(f)

    #         for _, channel, message in reader.iter_messages():
    #             encoding = channel.message_encoding

    #             # 只处理图像
    #             if encoding not in ["image/jpeg", "image/jpg", "image/png"]:
    #                 continue

    #             try:
    #                 # OpenCV快速解码
    #                 nparr = np.frombuffer(message.data, np.uint8)

    #                 if encoding in ["image/jpeg", "image/jpg"]:
    #                     img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    #                 else:  # PNG
    #                     img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
    #                     if img is not None and len(img.shape) == 2:
    #                         img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    #                 if img is None:
    #                     continue

    #                 # 记录第一帧尺寸
    #                 if frame_count == 0:
    #                     self.stats['height'], self.stats['width'] = img.shape[:2]

    #                 # 保存为PNG
    #                 frame_path = temp_dir / f"frame_{frame_count:06d}.png"
    #                 cv2.imwrite(str(frame_path), img)
    #                 frames.append(frame_path)

    #                 frame_count += 1

    #                 # if frame_count % 100 == 0:
    #                 #     print(f"已解码 {frame_count} 帧...")

    #             except Exception as e:
    #                 print(f"解码帧 {frame_count} 时出错: {e}")
    #                 continue

    #     self.stats['total_frames'] = frame_count
    #     self.stats['processed_frames'] = len(frames)
    #     return frames

    def extract_frames(self, input_file, temp_dir):
        """提取MCAP中的图像帧（保持顺序）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        frame_count = 0
        frame_paths = []

        try:
            with open(input_file, "rb") as f:
                reader = make_reader(f)

                # 收集所有解码任务
                decode_tasks = []

                for _, channel, message in reader.iter_messages():
                    encoding = channel.message_encoding

                    if encoding not in ["image/jpeg", "image/jpg", "image/png"]:
                        continue

                    # 记录任务信息（不立即解码）
                    decode_tasks.append({
                        'data': message.data,
                        'encoding': encoding,
                        'index': frame_count
                    })

                    if frame_count == 0:
                        # 需要解码第一帧获取尺寸
                        nparr = np.frombuffer(message.data, np.uint8)
                        if encoding in ["image/jpeg", "image/jpg"]:
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        else:
                            img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)

                        if img is not None:
                            self.stats['height'], self.stats['width'] = img.shape[:2]

                    frame_count += 1

                    # if frame_count % 100 == 0:
                    #     print(f"已准备 {frame_count} 帧...")

                # 使用线程池并行解码和保存，但保持顺序
                with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as executor:
                    # 提交所有任务，保持原始索引
                    future_to_index = {}
                    for task in decode_tasks:
                        future = executor.submit(
                            self._decode_and_save_frame,
                            task['data'],
                            task['encoding'],
                            task['index'],
                            temp_dir
                        )
                        future_to_index[future] = task['index']

                    # 预分配结果列表
                    frame_paths = [None] * len(decode_tasks)

                    # 按完成顺序处理，但按索引存储
                    for future in as_completed(future_to_index):
                        idx = future_to_index[future]
                        try:
                            result = future.result()
                            if result:
                                frame_paths[idx] = result
                                # if idx % 100 == 0:
                                #     print(f"已处理 {idx}/{len(decode_tasks)} 帧")
                        except Exception as e:
                            print(f"处理第 {idx} 帧时出错: {e}")

        except Exception as e:
            print(f"读取MCAP文件时出错: {e}")

        # 过滤掉None值
        valid_frames = [f for f in frame_paths if f is not None]
        self.stats['total_frames'] = frame_count
        self.stats['processed_frames'] = len(valid_frames)

        print(f"处理完成：总共 {frame_count} 帧，成功保存 {len(valid_frames)} 帧")
        return valid_frames

    def _decode_and_save_frame(self, data, encoding, index, temp_dir):
        """解码并保存单帧图像"""
        try:
            nparr = np.frombuffer(data, np.uint8)

            if encoding in ["image/jpeg", "image/jpg"]:
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:  # PNG
                img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
                if img is not None and len(img.shape) == 2:
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            if img is None:
                return None

            # 生成文件名
            frame_path = temp_dir / f"frame_{index:06d}.png"
            cv2.imwrite(str(frame_path), img)

            return frame_path

        except Exception as e:
            print(f"解码/保存第 {index} 帧时出错: {e}")
            return None


    def encode_video(self, frames_dir, output_file, use_nvenc):
        """使用ffmpeg编码视频"""
        try:
            # 获取CPU核心数
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
        except:
            cpu_count = 4

        # 构建ffmpeg命令
        if not use_nvenc:
            cmd = [
                'ffmpeg',
                '-y',
                '-framerate', str(self.fps),
                '-i', str(frames_dir / 'frame_%06d.png'),
                '-c:v', 'libaom-av1',
                '-crf', str(self.crf),
                '-cpu-used', str(self.cpu_used),
                '-pix_fmt', 'yuv420p',
                '-row-mt', '1',
                '-tile-columns', '2',
                '-tile-rows', '1',
                '-threads', str(cpu_count),
                '-movflags', '+faststart',
                str(output_file)
            ]
            print("使用软编码...")
        else:
            cmd = [
                'ffmpeg',
                '-y',
                '-framerate', str(self.fps),
                '-i', str(frames_dir / 'frame_%06d.png'),
                '-c:v', 'av1_nvenc',  # NVIDIA AV1硬件编码器
                '-preset', 'p4',       # p1-p7，p4是默认
                '-tune', 'hq',         # hq/high-quality/ll/ull
                '-rc', 'vbr',          # cbr/vbr/cbr_ld_hq
                '-cq', str(self.crf) if self.crf <= 51 else '34',  # NVENC使用CQ参数，类似CRF
                '-b:v', '0',           # 设为0让CQ生效
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                str(output_file)
            ]
            print("使用硬编码...")

        print("开始编码视频...")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # 显示进度
            for line in process.stdout:
                if 'frame=' in line.lower():
                    sys.stdout.write(f'\r{line.strip()}')
                    sys.stdout.flush()

            process.wait()

            if process.returncode == 0:
                return True
            else:
                return False

        except Exception as e:
            print(f"编码失败: {e}")
            return False

    def get_video_info(self, video_path):
        """
        使用ffprobe获取视频信息

        Returns:
            dict: 视频信息字典
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # ffprobe命令
        cmd = [
            'ffprobe',
            '-v', 'quiet',                    # 安静模式
            '-print_format', 'json',          # 输出JSON格式
            '-show_format',                   # 显示格式信息
            '-show_streams',                  # 显示流信息
            str(video_path)
        ]

        try:
            # 运行ffprobe
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            # 解析视频信息
            info = {
                "video.height": 0,
                "video.width": 0,
                "video.codec": "",
                "video.pix_fmt": "",
                "video.is_depth_map": False,
                "video.fps": 0,
                "video.channels": 3,  # 默认RGB/BGR
                "has_audio": False
            }

            # 查找视频流
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    # 基础信息
                    info["video.height"] = stream.get('height', 0)
                    info["video.width"] = stream.get('width', 0)
                    info["video.codec"] = stream.get('codec_name', '')
                    info["video.pix_fmt"] = stream.get('pix_fmt', '')

                    # 计算FPS
                    if 'r_frame_rate' in stream:
                        # 处理分数形式的fps，如 "30/1"
                        fps_str = stream['r_frame_rate']
                        if '/' in fps_str:
                            num, den = fps_str.split('/')
                            if den and float(den) != 0:
                                info["video.fps"] = int(float(num) / float(den))
                            else:
                                info["video.fps"] = int(float(num))
                        else:
                            info["video.fps"] = float(fps_str)

                    # 判断是否是深度图（基于编码器或像素格式）
                    if info["video.codec"] in ['dmb1', 'depth'] or 'depth' in info["video.pix_fmt"]:
                        info["video.is_depth_map"] = True
                        info["video.channels"] = 1  # 深度图通常是单通道

                    break  # 只处理第一个视频流

            # 检查是否有音频流
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'audio':
                    info["has_audio"] = True
                    break

            return info

        except subprocess.CalledProcessError as e:
            raise Exception(f"ffprobe执行失败: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"JSON解析失败: {e}")
        except Exception as e:
            raise Exception(f"获取视频信息失败: {e}")

    def convert(self, input_file, output_file, use_nvenc, show_progress=True):
        """
        执行转换 (支持H.265流式转换)

        Args:
            input_file: 输入MCAP文件路径
            output_file: 输出MP4文件路径
            use_nvenc: 是否使用NVIDIA硬件编码
            show_progress: 是否显示进度

        Returns:
            bool: 转换是否成功
        """
        # 检查输入文件
        input_path = Path(input_file)
        if not input_path.exists():
            print(f"错误: 输入文件不存在 {input_file}")
            return False

        # 检查ffmpeg
        if not self.check_ffmpeg():
            return False

        print(f"开始转换: {input_file} → {output_file}")
        total_start = time.time()

        try:
            import os

            try:
                cpu_count = os.cpu_count() or 4
            except:
                cpu_count = 4

            # 构建ffmpeg命令
            # 输入部分: 使用hevc解封装pipe:0
            cmd_base = [
                'ffmpeg', '-y',
                '-loglevel', 'error',
                '-stats',
                '-f', 'hevc',
                '-r', str(self.fps),
                '-i', 'pipe:0'
            ]

            # 编码部分
            if not use_nvenc:
                cmd_enc = [
                    '-c:v', 'libaom-av1',
                    '-crf', str(self.crf),
                    '-cpu-used', str(self.cpu_used),
                    '-threads', str(cpu_count),
                    '-row-mt', '1',
                    '-tile-columns', '2',
                    '-tile-rows', '1'
                ]
                print("使用软编码(AV1)...")
            else:
                cmd_enc = [
                    '-c:v', 'av1_nvenc',
                    '-preset', 'p4',
                    '-tune', 'hq',
                    '-rc', 'vbr',
                    '-cq', str(self.crf) if self.crf <= 51 else '42',
                    '-b:v', '0',
                    '-g', str(self.fps / 2),  # 强制长GOP（10秒），大幅减小静止画面体积
                    '-bf', '0',            # 增加 B 帧
                    '-temporal-aq', '1',    # 启用时域自适应量化
                    '-spatial-aq', '1',
                ]
                print("使用硬编码(AV1 NVENC)...")

            cmd_common = [
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                str(output_file)
            ]

            cmd = cmd_base + cmd_enc + cmd_common

            print("开始流式转换...")

            # 启动ffmpeg
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=None,
                stderr=None,
                bufsize=10*1024*1024
            )

            # 主线程写入数据
            try:
                with open(input_path, "rb") as f:
                    reader = make_reader(f)
                    count = 0
                    for _, channel, msg in reader.iter_messages():
                        if channel.message_encoding == "video/h265":
                            try:
                                process.stdin.write(msg.data)
                                count += 1
                            except BrokenPipeError:
                                break
                print(f"已流式传输 {count} 帧到ffmpeg")
                process.stdin.close()
            except Exception as e:
                print(f"写入管道失败: {e}")
                try:
                    process.stdin.close()
                except:
                    pass

            process.wait()

            self.stats['total_time'] = time.time() - total_start

            if process.returncode != 0:
                print(f"\n转换失败，ffmpeg返回码: {process.returncode}")
                return False

            # 检查输出文件
            output_path = Path(output_file)
            if output_path.exists():
                self.stats['output_size_mb'] = output_path.stat().st_size / (1024 * 1024)

            return True

        except Exception as e:
            print(f"\n转换异常: {e}")
            import traceback
            traceback.print_exc()
            return False

class JSONEditor:
    def __init__(self):
        self.file_path = None
        self.data = None

    def load(self):
        with open(self.file_path, encoding='utf-8') as f:
            self.data = json.load(f)
        return self

    def save(self, file_path, data):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return self

    def update_video_info(self, file_path, feature_name, video_info):
        """更新特定feature的info字段"""
        self.file_path = Path(file_path)
        self.load()

        if "features" in self.data and feature_name in self.data["features"]:
            self.data["features"][feature_name]["info"] = video_info
            print(f"✅ 已更新 {feature_name} 的info字段")
        else:
            print(f"❌ 未找到 {feature_name} 字段")

        self.save(Path(file_path), self.data)

class ParquetEditor:
    def __init__(self):
        self.file_path = None
        self.data = None

    def load(self, file_path):
        self.data = pd.read_parquet(file_path)
        # print(self.data)
        return self.data

    def save(self, df, path):
        df.to_parquet(path, index=False)

class ReProcessing:
    def __init__(self, dataset_path: Path, use_nvenc: bool):
        self.dataset_path = Path(dataset_path)
        self.use_nvenc = use_nvenc
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"路径不存在: {self.dataset_path}")

        if not self.dataset_path.is_dir():
            raise NotADirectoryError(f"路径不是文件夹: {self.dataset_path}")

        self.observation_keys = None
        self.mcap_path = {}
        self.video_path = {}
        self.fps = 0
        self.joint_num = 0
        self.total_episodes = 0
        self.stats = {}
        self.videos = {}

        self.get_dataset_info()

        self.converter = McapToMp4Converter(
            fps=self.fps,
            crf=18,
            cpu_used=6
        )

        self.json_editor = JSONEditor()
        self.parquet_editor = ParquetEditor()

    def get_folders_pathlib(self, path):
        folders = sorted(f.name for f in path.iterdir() if f.is_dir())
        return folders

    def get_dataset_info(self):
        self.observation_keys = self.get_folders_pathlib(self.dataset_path / "mcap")
        json_path = self.dataset_path / "meta" / "info.json"
        with open(str(json_path), encoding='utf-8') as f:
            data = json.load(f)
            self.fps = data['fps']
            self.total_episodes = data['total_episodes']
            # print(f"FPS值: {fps_value}")  # 输出: FPS值: 30

    def merge_mcap_files_simple(self, input_paths, output_path):
        """
        简化版合并，支持JPEG/PNG/H265消息合并

        Args:
            input_paths: list[Path] - MCAP文件路径列表
            output_path: Path - 输出MCAP文件路径

        Returns:
            bool: 合并是否成功
        """
        try:
            from mcap.writer import Writer
            import time as t
            from pathlib import Path

            output_path = Path(output_path)

            print(f"开始合并 {len(input_paths)} 个MCAP文件...")

            # 1. 扫描第一个有效文件获取topic和encoding信息
            target_topic = None
            target_encoding = None

            for input_path in input_paths:
                input_path = Path(input_path)
                if not input_path.exists():
                    continue

                try:
                    with open(input_path, "rb") as input_file:
                        reader = make_reader(input_file)
                        for schema, channel, message in reader.iter_messages():
                            if channel.message_encoding in ["image/jpeg", "image/png", "video/h265"]:
                                target_topic = channel.topic
                                target_encoding = channel.message_encoding
                                print(f"检测到消息格式: topic='{target_topic}', encoding='{target_encoding}'")
                                break
                    if target_topic:
                        break
                except Exception as e:
                    print(f"预扫描文件 {input_path} 失败: {e}")
                    continue

            if not target_topic:
                print("❌ 无法从输入文件中检测到有效的图像/视频消息")
                return False

            # 使用二进制写入模式打开文件
            with open(output_path, "wb") as f:
                writer = Writer(f)
                writer.start()

                channel_id = writer.register_channel(
                    schema_id=0,
                    topic=target_topic,
                    message_encoding=target_encoding
                )

                message_count = 0
                start_time = t.time_ns()

                for i, input_path in enumerate(input_paths):
                    input_path = Path(input_path)

                    if not input_path.exists():
                        print(f"警告: 文件不存在，跳过 {input_path}")
                        continue

                    print(f"处理文件 {i+1}/{len(input_paths)}: {input_path.name}")

                    try:
                        with open(input_path, "rb") as input_file:
                            reader = make_reader(input_file)

                            file_messages = 0

                            for _, channel, message in reader.iter_messages():
                                # 匹配 detected encoding
                                if channel.message_encoding == target_encoding:
                                    # 使用递增的时间戳，确保顺序
                                    current_time = start_time + message_count * 1000000  # 1ms间隔

                                    writer.add_message(
                                        channel_id=channel_id,
                                        log_time=current_time,
                                        publish_time=current_time,
                                        data=message.data,
                                        sequence=message_count
                                    )

                                    message_count += 1
                                    file_messages += 1

                            print(f"  提取 {file_messages} 条消息")

                    except Exception as e:
                        print(f"  处理文件 {input_path} 时出错: {e}")
                        continue

                # 重要：确保调用finish()
                writer.finish()

            # 检查文件是否成功创建
            if output_path.exists():
                file_size_mb = output_path.stat().st_size / (1024 * 1024)
                print(f"\n✅ 合并完成!")
                print(f"总计: {message_count} 条消息")
                print(f"输出文件: {output_path}")
                print(f"文件大小: {file_size_mb:.2f} MB")
                return True
            else:
                print(f"❌ 合并失败: 输出文件未创建")
                return False

        except Exception as e:
            print(f"❌ 合并失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def mcap_to_mp4(self):
        for mcap_key in self.observation_keys:
            self.mcap_path[mcap_key] = []
            episode_path = self.get_folders_pathlib(self.dataset_path / "mcap" / mcap_key)
            for i in range(self.total_episodes):
                self.mcap_path[mcap_key].append(self.dataset_path / "mcap" / mcap_key / episode_path[i] / f"{mcap_key}.mcap")
            self.merge_mcap_files_simple(self.mcap_path[mcap_key], self.dataset_path / "mcap" / mcap_key / f"{mcap_key}.mcap")

            self.video_path[mcap_key] = self.dataset_path / "videos" / mcap_key / "chunk-000"
            self.video_path[mcap_key].mkdir(parents=True, exist_ok=True)
            self.converter.convert(str(self.dataset_path / "mcap" / mcap_key / f"{mcap_key}.mcap"), str(self.video_path[mcap_key] / "file-000.mp4"), self.use_nvenc)

        try:
            shutil.rmtree(self.dataset_path / "mcap_temp")
            shutil.rmtree(self.dataset_path / "mcap")
        except Exception as e:
            print(f"清理临时文件失败: {e}")
        print("\n")

    def update_info(self):
        video_info = {}
        for video_key in self.observation_keys:
            # video_info[video_key] = []
            video_info[video_key] = self.converter.get_video_info(f"{self.dataset_path}/videos/{video_key}/chunk-000/file-000.mp4")
            self.json_editor.update_video_info(f"{self.dataset_path}/meta/info.json", video_key, video_info[video_key])

    def get_dataset_stats(self):
        file_path = self.dataset_path / "data" / "chunk-000" / "file-000.parquet"
        raw_data = self.parquet_editor.load(f"{file_path}")
        for i in range(self.total_episodes):
            self.stats[i] = {}
            self.stats[i]["timestamp"] = {}
            self.stats[i]["frame_index"] = {}
            self.stats[i]["episode_index"] = {}
            self.stats[i]["index"] = {}
            self.stats[i]["task_index"] = {}
            self.stats[i]["action"] = {}
            self.stats[i]["observation.state"] = {}

            selsct_data = raw_data[raw_data['episode_index'] == i]

            timestamp = selsct_data['timestamp']
            self.stats[i]["timestamp"]["min"] = timestamp.min()
            self.stats[i]["timestamp"]["max"] = timestamp.max()
            self.stats[i]["timestamp"]["mean"] = timestamp.mean()
            self.stats[i]["timestamp"]["std"] = timestamp.std()
            self.stats[i]["timestamp"]["count"] = len(selsct_data)
            self.stats[i]["timestamp"]["q01"] = float(np.percentile(timestamp, 1))
            self.stats[i]["timestamp"]["q10"] = float(np.percentile(timestamp, 10))
            self.stats[i]["timestamp"]["q50"] = float(np.percentile(timestamp, 50))
            self.stats[i]["timestamp"]["q90"] = float(np.percentile(timestamp, 90))
            self.stats[i]["timestamp"]["q99"] = float(np.percentile(timestamp, 99))

            frame_index = selsct_data['frame_index']
            self.stats[i]["frame_index"]["min"] = frame_index.min()
            self.stats[i]["frame_index"]["max"] = frame_index.max()
            self.stats[i]["frame_index"]["mean"] = frame_index.mean()
            self.stats[i]["frame_index"]["std"] = frame_index.std()
            self.stats[i]["frame_index"]["count"] = len(selsct_data)
            self.stats[i]["frame_index"]["q01"] = float(np.percentile(frame_index, 1))
            self.stats[i]["frame_index"]["q10"] = float(np.percentile(frame_index, 10))
            self.stats[i]["frame_index"]["q50"] = float(np.percentile(frame_index, 50))
            self.stats[i]["frame_index"]["q90"] = float(np.percentile(frame_index, 90))
            self.stats[i]["frame_index"]["q99"] = float(np.percentile(frame_index, 99))

            episode_index = selsct_data['episode_index']
            self.stats[i]["episode_index"]["min"] = episode_index.min()
            self.stats[i]["episode_index"]["max"] = episode_index.max()
            self.stats[i]["episode_index"]["mean"] = episode_index.mean()
            self.stats[i]["episode_index"]["std"] = episode_index.std()
            self.stats[i]["episode_index"]["count"] = len(selsct_data)
            self.stats[i]["episode_index"]["q01"] = float(np.percentile(episode_index, 1))
            self.stats[i]["episode_index"]["q10"] = float(np.percentile(episode_index, 10))
            self.stats[i]["episode_index"]["q50"] = float(np.percentile(episode_index, 50))
            self.stats[i]["episode_index"]["q90"] = float(np.percentile(episode_index, 90))
            self.stats[i]["episode_index"]["q99"] = float(np.percentile(episode_index, 99))

            index = selsct_data['index']
            self.stats[i]["index"]["min"] = index.min()
            self.stats[i]["index"]["max"] = index.max()
            self.stats[i]["index"]["mean"] = index.mean()
            self.stats[i]["index"]["std"] = index.std()
            self.stats[i]["index"]["count"] = len(selsct_data)
            self.stats[i]["index"]["q01"] = float(np.percentile(index, 1))
            self.stats[i]["index"]["q10"] = float(np.percentile(index, 10))
            self.stats[i]["index"]["q50"] = float(np.percentile(index, 50))
            self.stats[i]["index"]["q90"] = float(np.percentile(index, 90))
            self.stats[i]["index"]["q99"] = float(np.percentile(index, 99))

            task_index = selsct_data['task_index']
            self.stats[i]["task_index"]["min"] = task_index.min()
            self.stats[i]["task_index"]["max"] = task_index.max()
            self.stats[i]["task_index"]["mean"] = task_index.mean()
            self.stats[i]["task_index"]["std"] = task_index.std()
            self.stats[i]["task_index"]["count"] = len(selsct_data)
            self.stats[i]["task_index"]["q01"] = float(np.percentile(task_index, 1))
            self.stats[i]["task_index"]["q10"] = float(np.percentile(task_index, 10))
            self.stats[i]["task_index"]["q50"] = float(np.percentile(task_index, 50))
            self.stats[i]["task_index"]["q90"] = float(np.percentile(task_index, 90))
            self.stats[i]["task_index"]["q99"] = float(np.percentile(task_index, 99))

            action = selsct_data['action']
            stack_action = np.stack(action.values)
            self.stats[i]["action"]["min"] = stack_action.min(axis=0)
            self.stats[i]["action"]["max"] = stack_action.max(axis=0)
            self.stats[i]["action"]["mean"] = stack_action.mean(axis=0)
            self.stats[i]["action"]["std"] = stack_action.std(axis=0)
            self.stats[i]["action"]["count"] = len(selsct_data)
            self.stats[i]["action"]["q01"] = np.percentile(stack_action, 1, axis=0).tolist()
            self.stats[i]["action"]["q10"] = np.percentile(stack_action, 10, axis=0).tolist()
            self.stats[i]["action"]["q50"] = np.percentile(stack_action, 50, axis=0).tolist()
            self.stats[i]["action"]["q90"] = np.percentile(stack_action, 90, axis=0).tolist()
            self.stats[i]["action"]["q99"] = np.percentile(stack_action, 99, axis=0).tolist()

            observation_state = selsct_data['observation.state']
            stack_observation_state = np.stack(observation_state.values)
            self.stats[i]["observation.state"]["min"] = stack_observation_state.min(axis=0)
            self.stats[i]["observation.state"]["max"] = stack_observation_state.max(axis=0)
            self.stats[i]["observation.state"]["mean"] = stack_observation_state.mean(axis=0)
            self.stats[i]["observation.state"]["std"] = stack_observation_state.std(axis=0)
            self.stats[i]["observation.state"]["count"] = len(selsct_data)
            self.stats[i]["observation.state"]["q01"] = np.percentile(stack_observation_state, 1, axis=0).tolist()
            self.stats[i]["observation.state"]["q10"] = np.percentile(stack_observation_state, 10, axis=0).tolist()
            self.stats[i]["observation.state"]["q50"] = np.percentile(stack_observation_state, 50, axis=0).tolist()
            self.stats[i]["observation.state"]["q90"] = np.percentile(stack_observation_state, 90, axis=0).tolist()
            self.stats[i]["observation.state"]["q99"] = np.percentile(stack_observation_state, 99, axis=0).tolist()

        self.fps = len(self.stats[0]["action"]["min"])

        return self.stats

    def get_dataset_videos(self):
        for i in range(self.total_episodes):
            self.videos[i] = {}
            for video_key in self.observation_keys:
                self.videos[i][video_key] = {}
                self.videos[i][video_key]["chunk_index"] = 0
                self.videos[i][video_key]["file_index"] = 0

                if i == 0:
                    self.videos[i][video_key]["from_timestamp"] = 0.0
                    self.videos[i][video_key]["to_timestamp"] = self.stats[i]["frame_index"]["count"] / self.fps
                else:
                    self.videos[i][video_key]["from_timestamp"] = self.videos[i-1][video_key]["to_timestamp"]
                    self.videos[i][video_key]["to_timestamp"] = self.videos[i][video_key]["from_timestamp"] + self.stats[i]["frame_index"]["count"] / self.fps

        self.videos = self.convert_numpy_to_python(self.videos)

        return self.videos

    def estimate_num_samples(
        self, dataset_len: int, min_num_samples: int = 100, max_num_samples: int = 10_000, power: float = 0.75
    ) -> int:
        if dataset_len < min_num_samples:
            min_num_samples = dataset_len
        return max(min_num_samples, min(int(dataset_len**power), max_num_samples))

    def sample_indices(self, data_len: int) -> list[int]:
        num_samples = self.estimate_num_samples(data_len)
        return np.round(np.linspace(0, data_len - 1, num_samples)).astype(int).tolist()

    def auto_downsample_height_width(self, img: np.ndarray, target_size: int = 150, max_size_threshold: int = 300):
        _, height, width = img.shape

        if max(width, height) < max_size_threshold:
            # no downsampling needed
            return img

        downsample_factor = int(width / target_size) if width > height else int(height / target_size)
        return img[:, ::downsample_factor, ::downsample_factor]

    def extract_frame_from_mp4(self, video_path, frame_index):
        """使用PyAV处理AV1编码视频"""
        try:
            with av.open(str(video_path)) as container:
                stream = container.streams.video[0]

                # 获取帧率和分辨率
                fps = stream.average_rate or 30
                height, width = stream.height or 480, stream.width or 640

                # seek到目标位置
                timestamp = frame_index / float(fps)
                container.seek(
                    int(timestamp * av.time_base),
                    stream=stream,
                    backward=True,
                    any_frame=False
                )

                # 读取第一帧
                for frame in container.decode(stream):
                    # 转换为float32并归一化
                    img = frame.to_ndarray(format='rgb24')
                    img_float = img.astype(np.float32) / 255.0
                    img_float = np.transpose(img_float, (2, 0, 1))
                    img_float = self.auto_downsample_height_width(img_float)
                    return img_float  # 成功返回

        except Exception:
            print("seek failed")  # 静默失败

    def get_cam_stats(self):
        from collections import deque

        start_time_all = time.time()
        mode_info = "开启硬件解码(CUDA)" if self.use_nvenc else "使用软件解码(CPU)"
        print(f"开始计算摄像头统计信息 (FFmpeg Pipe Mode) - [{mode_info}]...")

        # 1. 预先计算每个episode的全局偏移量
        episode_offsets = [0] * self.total_episodes
        current_offset = 0
        for i in range(self.total_episodes):
            episode_offsets[i] = current_offset
            current_offset += self.stats[i]["frame_index"]["count"]

        # 辅助函数：保存统计数据
        def save_stats(ep_idx, v_key, img_list, dummy_ref):
            if not img_list and dummy_ref is not None:
                img_list = [dummy_ref]

            if not img_list:
                return

            arr = np.stack(img_list)
            # 计算统计量
            axes = (0, 2, 3)
            self.stats[ep_idx][v_key]["min"] = np.min(arr, axis=axes)
            self.stats[ep_idx][v_key]["max"] = np.max(arr, axis=axes)
            self.stats[ep_idx][v_key]["mean"] = np.mean(arr, axis=axes)
            self.stats[ep_idx][v_key]["std"] = np.std(arr, axis=axes)
            self.stats[ep_idx][v_key]["count"] = len(img_list)
            self.stats[ep_idx][v_key]["q01"] = np.quantile(arr, 0.01, axis=axes)
            self.stats[ep_idx][v_key]["q10"] = np.quantile(arr, 0.1, axis=axes)
            self.stats[ep_idx][v_key]["q50"] = np.quantile(arr, 0.5, axis=axes)
            self.stats[ep_idx][v_key]["q90"] = np.quantile(arr, 0.9, axis=axes)
            self.stats[ep_idx][v_key]["q99"] = np.quantile(arr, 0.99, axis=axes)

        for video_key in self.observation_keys:
            step_start = time.time()
            # print(f"正在处理视频: {video_key}")
            video_path = self.video_path[video_key] / "file-000.mp4"

            # 2. 构建全局请求队列
            t_prep = time.time()
            frame_requests = []
            for i in range(self.total_episodes):
                self.stats[i][video_key] = {}
                cnt = self.stats[i]["frame_index"]["count"]
                if cnt > 0:
                    l_indices = self.sample_indices(cnt)
                    offset = episode_offsets[i]
                    for li in l_indices:
                        frame_requests.append((offset + li, i))

            if not frame_requests:
                continue

            # 按帧号排序
            request_queue = deque(sorted(frame_requests, key=lambda x: x[0]))
            # print(f"  请求队列构建完成: {len(request_queue)} 帧")

            # 3. 获取视频元数据 (使用av.open快速读取一次)
            try:
                with av.open(str(video_path)) as container:
                    stream = container.streams.video[0]
                    src_w = stream.width or 640
                    src_h = stream.height or 480
                    fps = stream.average_rate or 30
            except Exception as e:
                print(f"  获取视频信息失败: {e}")
                continue

            # 4. 计算缩放参数
            target_size = 150
            max_thr = 300
            new_w, new_h = src_w, src_h
            if max(src_w, src_h) >= max_thr:
                scale = max(1, int(src_w / target_size) if src_w > src_h else int(src_h / target_size))
                new_w, new_h = src_w // scale, src_h // scale

            # print(f"  分辨率: {src_w}x{src_h} -> {new_w}x{new_h}")

            # 5. 启动 FFmpeg 子进程进行解码和缩放
            # 构建命令: hwaccel -> input -> scale filter -> rawvideo output
            cmd = ['ffmpeg', '-y']
            if self.use_nvenc:
                cmd.extend(['-hwaccel', 'cuda']) # 启用CUDA硬解

            cmd.extend(['-v', 'error', '-i', str(video_path)])
            cmd.extend(['-vf', f'scale={new_w}:{new_h}']) # 在FFmpeg端进行缩放
            cmd.extend(['-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'])

            process = None
            try:
                t_loop_start = time.time()
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**7)

                dummy_frame = np.zeros((3, new_h, new_w), dtype=np.float32)
                frame_idx = 0
                frame_size_bytes = new_w * new_h * 3

                current_ep_idx = -1
                current_ep_images = []
                processed_count = 0

                # 开始逐帧读取管道
                while request_queue:
                    # 获取我们要找的下一个目标帧号
                    target_global_idx, target_ep_idx = request_queue[0] # peek

                    # 管道读取：如果当前帧号还没到目标帧，就一直读并丢弃（或者刚好从头读）
                    while frame_idx <= target_global_idx:
                        raw_bytes = process.stdout.read(frame_size_bytes)
                        if not raw_bytes or len(raw_bytes) != frame_size_bytes:
                            # 管道意外结束
                            raise EOFError("Video stream ended unexpectedly")

                        # 如果当前帧正是我们需要的
                        if frame_idx == target_global_idx:
                            # 处理匹配的帧
                            while request_queue and request_queue[0][0] == frame_idx:
                                _, tgt_ep = request_queue.popleft()

                                # 切换 Episode
                                if tgt_ep != current_ep_idx:
                                    if current_ep_idx != -1:
                                        save_stats(current_ep_idx, video_key, current_ep_images, dummy_frame)
                                    current_ep_idx = tgt_ep
                                    current_ep_images = []

                                # 转换为 numpy 并归一化
                                # (fromBuffer很快，因为数据量已经很小了)
                                img = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((new_h, new_w, 3))
                                img = img.astype(np.float32) / 255.0
                                img = np.transpose(img, (2, 0, 1)) # HWC -> CHW
                                current_ep_images.append(img)
                                processed_count += 1

                        frame_idx += 1

                # 循环结束，保存最后一组
                if current_ep_idx != -1:
                    save_stats(current_ep_idx, video_key, current_ep_images, dummy_frame)

                # print(f"  处理循环耗时: {time.time()-t_loop_start:.4f}s (Frames: {processed_count})")

            except Exception as e:
                print(f"  FFmpeg处理异常: {e}")
                import traceback
                traceback.print_exc()
            finally:
                if process:
                    process.terminate()
                    process.wait()

            # print(f"  单视频总耗时: {time.time()-step_start:.4f}s")

        # print(f"所有摄像头统计计算完成，总耗时: {time.time()-start_time_all:.4f}s")
        return self.stats


    def _convert_numpy_to_python(self, data_dict):
        """将numpy类型转换为Python原生类型"""
        converted = {}

        for key, value in data_dict.items():
            if isinstance(value, np.integer):
                # numpy整数 -> Python int
                converted[key] = int(value)
            elif isinstance(value, np.floating):
                # numpy浮点数 -> Python float
                converted[key] = float(value)
            elif isinstance(value, np.ndarray):
                # numpy数组 -> Python列表
                converted[key] = value.tolist()
            elif isinstance(value, np.bool_):
                # numpy布尔 -> Python bool
                converted[key] = bool(value)
            elif isinstance(value, np.str_):
                # numpy字符串 -> Python str
                converted[key] = str(value)
            else:
                # 其他类型保持原样
                converted[key] = value

        return converted

    def convert_numpy_to_python(self, data):
        """递归转换所有numpy类型为Python原生类型"""
        if isinstance(data, dict):
            # 递归处理字典
            return {key: self.convert_numpy_to_python(value) for key, value in data.items()}
        elif isinstance(data, (list, tuple)):
            # 递归处理列表/元组
            return [self.convert_numpy_to_python(item) for item in data]
        elif isinstance(data, np.integer):
            # numpy整数 -> Python int
            return int(data)
        elif isinstance(data, np.floating):
            # numpy浮点数 -> Python float
            return float(data)
        elif isinstance(data, np.ndarray):
            # numpy数组 -> Python列表
            return data.tolist()
        elif isinstance(data, np.bool_):
            # numpy布尔 -> Python bool
            return bool(data)
        elif isinstance(data, np.str_):
            # numpy字符串 -> Python str
            return str(data)
        else:
            # 其他类型保持原样
            return data

    def _build_parquet_data(self, episode_idx):
        """构建单行数据"""
        row = {}

        row['episode_index'] = self.stats[episode_idx]["episode_index_top"]
        row['tasks'] = self.stats[episode_idx]["tasks"]
        row['length'] = self.stats[episode_idx]["length"]
        row['data/chunk_index'] = self.stats[episode_idx]["data/chunk_index"]
        row['data/file_index'] = self.stats[episode_idx]["data/file_index"]
        row['dataset_from_index'] = self.stats[episode_idx]["dataset_from_index"]
        row['dataset_to_index'] = self.stats[episode_idx]["dataset_to_index"]

        for video_key in self.observation_keys:
            row[f'videos/{video_key}/chunk_index'] = self.videos[episode_idx][video_key]["chunk_index"]
            row[f'videos/{video_key}/file_index'] = self.videos[episode_idx][video_key]["file_index"]
            row[f'videos/{video_key}/from_timestamp'] = self.videos[episode_idx][video_key]["from_timestamp"]
            row[f'videos/{video_key}/to_timestamp'] = self.videos[episode_idx][video_key]["to_timestamp"]

        row['stats/action/min'] = self.stats[episode_idx]["action"]["min"]
        row['stats/action/max'] = self.stats[episode_idx]["action"]["max"]
        row['stats/action/mean'] = self.stats[episode_idx]["action"]["mean"]
        row['stats/action/std'] = self.stats[episode_idx]["action"]["std"]
        row['stats/action/count'] = [self.stats[episode_idx]["action"]["count"]]
        row['stats/action/q01'] = self.stats[episode_idx]["action"]["q01"]
        row['stats/action/q10'] = self.stats[episode_idx]["action"]["q10"]
        row['stats/action/q50'] = self.stats[episode_idx]["action"]["q50"]
        row['stats/action/q90'] = self.stats[episode_idx]["action"]["q90"]
        row['stats/action/q99'] = self.stats[episode_idx]["action"]["q99"]

        row['stats/observation.state/min'] = self.stats[episode_idx]["observation.state"]["min"]
        row['stats/observation.state/max'] = self.stats[episode_idx]["observation.state"]["max"]
        row['stats/observation.state/mean'] = self.stats[episode_idx]["observation.state"]["mean"]
        row['stats/observation.state/std'] = self.stats[episode_idx]["observation.state"]["std"]
        row['stats/observation.state/count'] = [self.stats[episode_idx]["observation.state"]["count"]]
        row['stats/observation.state/q01'] = self.stats[episode_idx]["observation.state"]["q01"]
        row['stats/observation.state/q10'] = self.stats[episode_idx]["observation.state"]["q10"]
        row['stats/observation.state/q50'] = self.stats[episode_idx]["observation.state"]["q50"]
        row['stats/observation.state/q90'] = self.stats[episode_idx]["observation.state"]["q90"]
        row['stats/observation.state/q99'] = self.stats[episode_idx]["observation.state"]["q99"]

        for video_key in self.observation_keys:
            row[f'stats/{video_key}/min'] = [[[value]] for value in self.stats[episode_idx][video_key]["min"]]
            row[f'stats/{video_key}/max'] = [[[value]] for value in self.stats[episode_idx][video_key]["max"]]
            row[f'stats/{video_key}/mean'] = [[[value]] for value in self.stats[episode_idx][video_key]["mean"]]
            row[f'stats/{video_key}/std'] = [[[value]] for value in self.stats[episode_idx][video_key]["std"]]
            row[f'stats/{video_key}/count'] = [self.stats[episode_idx][video_key]["count"]]
            row[f'stats/{video_key}/q01'] = [[[value]] for value in self.stats[episode_idx][video_key]["q01"]]
            row[f'stats/{video_key}/q10'] = [[[value]] for value in self.stats[episode_idx][video_key]["q10"]]
            row[f'stats/{video_key}/q50'] = [[[value]] for value in self.stats[episode_idx][video_key]["q50"]]
            row[f'stats/{video_key}/q90'] = [[[value]] for value in self.stats[episode_idx][video_key]["q90"]]
            row[f'stats/{video_key}/q99'] = [[[value]] for value in self.stats[episode_idx][video_key]["q99"]]

        row['stats/timestamp/min'] = [self.stats[episode_idx]["timestamp"]["min"]]
        row['stats/timestamp/max'] = [self.stats[episode_idx]["timestamp"]["max"]]
        row['stats/timestamp/mean'] = [self.stats[episode_idx]["timestamp"]["mean"]]
        row['stats/timestamp/std'] = [self.stats[episode_idx]["timestamp"]["std"]]
        row['stats/timestamp/count'] = [self.stats[episode_idx]["timestamp"]["count"]]
        row['stats/timestamp/q01'] = [self.stats[episode_idx]["timestamp"]["q01"]]
        row['stats/timestamp/q10'] = [self.stats[episode_idx]["timestamp"]["q10"]]
        row['stats/timestamp/q50'] = [self.stats[episode_idx]["timestamp"]["q50"]]
        row['stats/timestamp/q90'] = [self.stats[episode_idx]["timestamp"]["q90"]]
        row['stats/timestamp/q99'] = [self.stats[episode_idx]["timestamp"]["q99"]]

        row['stats/frame_index/min'] = [self.stats[episode_idx]["frame_index"]["min"]]
        row['stats/frame_index/max'] = [self.stats[episode_idx]["frame_index"]["max"]]
        row['stats/frame_index/mean'] = [self.stats[episode_idx]["frame_index"]["mean"]]
        row['stats/frame_index/std'] = [self.stats[episode_idx]["frame_index"]["std"]]
        row['stats/frame_index/count'] = [self.stats[episode_idx]["frame_index"]["count"]]
        row['stats/frame_index/q01'] = [self.stats[episode_idx]["frame_index"]["q01"]]
        row['stats/frame_index/q10'] = [self.stats[episode_idx]["frame_index"]["q10"]]
        row['stats/frame_index/q50'] = [self.stats[episode_idx]["frame_index"]["q50"]]
        row['stats/frame_index/q90'] = [self.stats[episode_idx]["frame_index"]["q90"]]
        row['stats/frame_index/q99'] = [self.stats[episode_idx]["frame_index"]["q99"]]

        row['stats/episode_index/min'] = [self.stats[episode_idx]["episode_index"]["min"]]
        row['stats/episode_index/max'] = [self.stats[episode_idx]["episode_index"]["max"]]
        row['stats/episode_index/mean'] = [self.stats[episode_idx]["episode_index"]["mean"]]
        row['stats/episode_index/std'] = [self.stats[episode_idx]["episode_index"]["std"]]
        row['stats/episode_index/count'] = [self.stats[episode_idx]["episode_index"]["count"]]
        row['stats/episode_index/q01'] = [self.stats[episode_idx]["episode_index"]["q01"]]
        row['stats/episode_index/q10'] = [self.stats[episode_idx]["episode_index"]["q10"]]
        row['stats/episode_index/q50'] = [self.stats[episode_idx]["episode_index"]["q50"]]
        row['stats/episode_index/q90'] = [self.stats[episode_idx]["episode_index"]["q90"]]
        row['stats/episode_index/q99'] = [self.stats[episode_idx]["episode_index"]["q99"]]

        row['stats/index/min'] = [self.stats[episode_idx]["index"]["min"]]
        row['stats/index/max'] = [self.stats[episode_idx]["index"]["max"]]
        row['stats/index/mean'] = [self.stats[episode_idx]["index"]["mean"]]
        row['stats/index/std'] = [self.stats[episode_idx]["index"]["std"]]
        row['stats/index/count'] = [self.stats[episode_idx]["index"]["count"]]
        row['stats/index/q01'] = [self.stats[episode_idx]["index"]["q01"]]
        row['stats/index/q10'] = [self.stats[episode_idx]["index"]["q10"]]
        row['stats/index/q50'] = [self.stats[episode_idx]["index"]["q50"]]
        row['stats/index/q90'] = [self.stats[episode_idx]["index"]["q90"]]
        row['stats/index/q99'] = [self.stats[episode_idx]["index"]["q99"]]

        row['stats/task_index/min'] = [self.stats[episode_idx]["task_index"]["min"]]
        row['stats/task_index/max'] = [self.stats[episode_idx]["task_index"]["max"]]
        row['stats/task_index/mean'] = [self.stats[episode_idx]["task_index"]["mean"]]
        row['stats/task_index/std'] = [self.stats[episode_idx]["task_index"]["std"]]
        row['stats/task_index/count'] = [self.stats[episode_idx]["task_index"]["count"]]
        row['stats/task_index/q01'] = [self.stats[episode_idx]["task_index"]["q01"]]
        row['stats/task_index/q10'] = [self.stats[episode_idx]["task_index"]["q10"]]
        row['stats/task_index/q50'] = [self.stats[episode_idx]["task_index"]["q50"]]
        row['stats/task_index/q90'] = [self.stats[episode_idx]["task_index"]["q90"]]
        row['stats/task_index/q99'] = [self.stats[episode_idx]["task_index"]["q99"]]

        row['meta/episodes/chunk_index'] = self.stats[episode_idx]["meta/episodes/chunk_index"]
        row['meta/episodes/file_index'] = self.stats[episode_idx]["meta/episodes/file_index"]

        return row

    def save_meta_parquet(self):
        file_path = self.dataset_path / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
        raw_data = self.parquet_editor.load(f"{file_path}")
        # print(raw_data)
        for i in range(self.total_episodes):
            selsct_data = raw_data[raw_data['episode_index'] == i]
            self.stats[i]["episode_index_top"] = selsct_data["episode_index"].iloc[0]
            self.stats[i]["tasks"] = selsct_data["tasks"].iloc[0]
            self.stats[i]["length"] = selsct_data["length"].iloc[0]
            self.stats[i]["data/chunk_index"] = selsct_data["data/chunk_index"].iloc[0]
            self.stats[i]["data/file_index"] = selsct_data["data/file_index"].iloc[0]
            self.stats[i]["dataset_from_index"] = selsct_data["dataset_from_index"].iloc[0]
            self.stats[i]["dataset_to_index"] = selsct_data["dataset_to_index"].iloc[0]
            self.stats[i]["meta/episodes/chunk_index"] = selsct_data["meta/episodes/chunk_index"].iloc[0]
            self.stats[i]["meta/episodes/file_index"] = selsct_data["meta/episodes/file_index"].iloc[0]

        self.stats = self.convert_numpy_to_python(self.stats)

        all_rows = []
        for i in range(self.total_episodes):
            # print(f"构建 episode {i} 的数据...")

            # 创建当前行的字典
            row_data = self._build_parquet_data(i)
            all_rows.append(row_data)

        df = pd.DataFrame(all_rows)
        old_path = self.dataset_path / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
        output_path = self.dataset_path / "meta" / "episodes" / "chunk-000" / "file-000.parquet"

        if os.path.exists(old_path):
            os.remove(old_path)

        df.to_parquet(str(output_path), engine='pyarrow')


        # return self.stats

    def save_meta_stats(self):
        meta_stats = {}
        meta_stats["timestamp"] = {}
        meta_stats["frame_index"] = {}
        meta_stats["episode_index"] = {}
        meta_stats["index"] = {}
        meta_stats["task_index"] = {}
        meta_stats["action"] = {}
        meta_stats["observation.state"] = {}

        meta_stats["timestamp"]["min"] = np.array([self.stats[i]["timestamp"]["min"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["max"] = np.array([self.stats[i]["timestamp"]["max"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["mean"] = np.array([self.stats[i]["timestamp"]["mean"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["std"] = np.array([self.stats[i]["timestamp"]["std"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["count"] = np.array([self.stats[i]["timestamp"]["count"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["q01"] = np.array([self.stats[i]["timestamp"]["q01"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["q10"] = np.array([self.stats[i]["timestamp"]["q10"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["q50"] = np.array([self.stats[i]["timestamp"]["q50"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["q90"] = np.array([self.stats[i]["timestamp"]["q90"] for i in range(self.total_episodes)])
        meta_stats["timestamp"]["q99"] = np.array([self.stats[i]["timestamp"]["q99"] for i in range(self.total_episodes)])

        meta_stats["frame_index"]["min"] = np.array([self.stats[i]["frame_index"]["min"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["max"] = np.array([self.stats[i]["frame_index"]["max"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["mean"] = np.array([self.stats[i]["frame_index"]["mean"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["std"] = np.array([self.stats[i]["frame_index"]["std"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["count"] = np.array([self.stats[i]["frame_index"]["count"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["q01"] = np.array([self.stats[i]["frame_index"]["q01"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["q10"] = np.array([self.stats[i]["frame_index"]["q10"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["q50"] = np.array([self.stats[i]["frame_index"]["q50"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["q90"] = np.array([self.stats[i]["frame_index"]["q90"] for i in range(self.total_episodes)])
        meta_stats["frame_index"]["q99"] = np.array([self.stats[i]["frame_index"]["q99"] for i in range(self.total_episodes)])

        meta_stats["episode_index"]["min"] = np.array([self.stats[i]["episode_index"]["min"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["max"] = np.array([self.stats[i]["episode_index"]["max"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["mean"] = np.array([self.stats[i]["episode_index"]["mean"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["std"] = np.array([self.stats[i]["episode_index"]["std"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["count"] = np.array([self.stats[i]["episode_index"]["count"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["q01"] = np.array([self.stats[i]["episode_index"]["q01"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["q10"] = np.array([self.stats[i]["episode_index"]["q10"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["q50"] = np.array([self.stats[i]["episode_index"]["q50"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["q90"] = np.array([self.stats[i]["episode_index"]["q90"] for i in range(self.total_episodes)])
        meta_stats["episode_index"]["q99"] = np.array([self.stats[i]["episode_index"]["q99"] for i in range(self.total_episodes)])

        meta_stats["index"]["min"] = np.array([self.stats[i]["index"]["min"] for i in range(self.total_episodes)])
        meta_stats["index"]["max"] = np.array([self.stats[i]["index"]["max"] for i in range(self.total_episodes)])
        meta_stats["index"]["mean"] = np.array([self.stats[i]["index"]["mean"] for i in range(self.total_episodes)])
        meta_stats["index"]["std"] = np.array([self.stats[i]["index"]["std"] for i in range(self.total_episodes)])
        meta_stats["index"]["count"] = np.array([self.stats[i]["index"]["count"] for i in range(self.total_episodes)])
        meta_stats["index"]["q01"] = np.array([self.stats[i]["index"]["q01"] for i in range(self.total_episodes)])
        meta_stats["index"]["q10"] = np.array([self.stats[i]["index"]["q10"] for i in range(self.total_episodes)])
        meta_stats["index"]["q50"] = np.array([self.stats[i]["index"]["q50"] for i in range(self.total_episodes)])
        meta_stats["index"]["q90"] = np.array([self.stats[i]["index"]["q90"] for i in range(self.total_episodes)])
        meta_stats["index"]["q99"] = np.array([self.stats[i]["index"]["q99"] for i in range(self.total_episodes)])

        meta_stats["task_index"]["min"] = np.array([self.stats[i]["task_index"]["min"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["max"] = np.array([self.stats[i]["task_index"]["max"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["mean"] = np.array([self.stats[i]["task_index"]["mean"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["std"] = np.array([self.stats[i]["task_index"]["std"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["count"] = np.array([self.stats[i]["task_index"]["count"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["q01"] = np.array([self.stats[i]["task_index"]["q01"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["q10"] = np.array([self.stats[i]["task_index"]["q10"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["q50"] = np.array([self.stats[i]["task_index"]["q50"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["q90"] = np.array([self.stats[i]["task_index"]["q90"] for i in range(self.total_episodes)])
        meta_stats["task_index"]["q99"] = np.array([self.stats[i]["task_index"]["q99"] for i in range(self.total_episodes)])

        meta_stats["action"]["min"] = np.array([self.stats[i]["action"]["min"] for i in range(self.total_episodes)])
        meta_stats["action"]["max"] = np.array([self.stats[i]["action"]["max"] for i in range(self.total_episodes)])
        meta_stats["action"]["mean"] = np.array([self.stats[i]["action"]["mean"] for i in range(self.total_episodes)])
        meta_stats["action"]["std"] = np.array([self.stats[i]["action"]["std"] for i in range(self.total_episodes)])
        meta_stats["action"]["count"] = np.array([self.stats[i]["action"]["count"] for i in range(self.total_episodes)])
        meta_stats["action"]["q01"] = np.array([self.stats[i]["action"]["q01"] for i in range(self.total_episodes)])
        meta_stats["action"]["q10"] = np.array([self.stats[i]["action"]["q10"] for i in range(self.total_episodes)])
        meta_stats["action"]["q50"] = np.array([self.stats[i]["action"]["q50"] for i in range(self.total_episodes)])
        meta_stats["action"]["q90"] = np.array([self.stats[i]["action"]["q90"] for i in range(self.total_episodes)])
        meta_stats["action"]["q99"] = np.array([self.stats[i]["action"]["q99"] for i in range(self.total_episodes)])

        meta_stats["observation.state"]["min"] = np.array([self.stats[i]["observation.state"]["min"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["max"] = np.array([self.stats[i]["observation.state"]["max"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["mean"] = np.array([self.stats[i]["observation.state"]["mean"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["std"] = np.array([self.stats[i]["observation.state"]["std"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["count"] = np.array([self.stats[i]["observation.state"]["count"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["q01"] = np.array([self.stats[i]["observation.state"]["q01"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["q10"] = np.array([self.stats[i]["observation.state"]["q10"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["q50"] = np.array([self.stats[i]["observation.state"]["q50"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["q90"] = np.array([self.stats[i]["observation.state"]["q90"] for i in range(self.total_episodes)])
        meta_stats["observation.state"]["q99"] = np.array([self.stats[i]["observation.state"]["q99"] for i in range(self.total_episodes)])

        for video_key in self.observation_keys:
            meta_stats[f"{video_key}"] = {}
            meta_stats[f"{video_key}"]["min"] = np.array([self.stats[i][f"{video_key}"]["min"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["max"] = np.array([self.stats[i][f"{video_key}"]["max"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["mean"] = np.array([self.stats[i][f"{video_key}"]["mean"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["std"] = np.array([self.stats[i][f"{video_key}"]["std"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["count"] = np.array([self.stats[i][f"{video_key}"]["count"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["q01"] = np.array([self.stats[i][f"{video_key}"]["q01"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["q10"] = np.array([self.stats[i][f"{video_key}"]["q10"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["q50"] = np.array([self.stats[i][f"{video_key}"]["q50"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["q90"] = np.array([self.stats[i][f"{video_key}"]["q90"] for i in range(self.total_episodes)])
            meta_stats[f"{video_key}"]["q99"] = np.array([self.stats[i][f"{video_key}"]["q99"] for i in range(self.total_episodes)])

        aggregate_stats = {}
        aggregate_stats["timestamp"] = {}
        aggregate_stats["frame_index"] = {}
        aggregate_stats["episode_index"] = {}
        aggregate_stats["index"] = {}
        aggregate_stats["task_index"] = {}
        aggregate_stats["action"] = {}
        aggregate_stats["observation.state"] = {}

        aggregate_stats["timestamp"]["min"] = np.min(meta_stats["timestamp"]["min"])
        aggregate_stats["timestamp"]["max"] = np.max(meta_stats["timestamp"]["max"])
        aggregate_stats["frame_index"]["min"] = np.min(meta_stats["frame_index"]["min"])
        aggregate_stats["frame_index"]["max"] = np.max(meta_stats["frame_index"]["max"])
        aggregate_stats["episode_index"]["min"] = np.min(meta_stats["episode_index"]["min"])
        aggregate_stats["episode_index"]["max"] = np.max(meta_stats["episode_index"]["max"])
        aggregate_stats["index"]["min"] = np.min(meta_stats["index"]["min"])
        aggregate_stats["index"]["max"] = np.max(meta_stats["index"]["max"])
        aggregate_stats["task_index"]["min"] = np.min(meta_stats["task_index"]["min"])
        aggregate_stats["task_index"]["max"] = np.max(meta_stats["task_index"]["max"])

        aggregate_stats["timestamp"]["count"] = np.sum(meta_stats["timestamp"]["count"])
        aggregate_stats["frame_index"]["count"] = np.sum(meta_stats["frame_index"]["count"])
        aggregate_stats["episode_index"]["count"] = np.sum(meta_stats["episode_index"]["count"])
        aggregate_stats["index"]["count"] = np.sum(meta_stats["index"]["count"])
        aggregate_stats["task_index"]["count"] = np.sum(meta_stats["task_index"]["count"])

        aggregate_stats["timestamp"]["mean"] = np.sum(meta_stats["timestamp"]["mean"] * meta_stats["timestamp"]["count"]) / aggregate_stats["timestamp"]["count"]
        aggregate_stats["frame_index"]["mean"] = np.sum(meta_stats["frame_index"]["mean"] * meta_stats["frame_index"]["count"]) / aggregate_stats["frame_index"]["count"]
        aggregate_stats["episode_index"]["mean"] = np.sum(meta_stats["episode_index"]["mean"] * meta_stats["episode_index"]["count"]) / aggregate_stats["episode_index"]["count"]
        aggregate_stats["index"]["mean"] = np.sum(meta_stats["index"]["mean"] * meta_stats["index"]["count"]) / aggregate_stats["index"]["count"]
        aggregate_stats["task_index"]["mean"] = np.sum(meta_stats["task_index"]["mean"] * meta_stats["task_index"]["count"]) / aggregate_stats["task_index"]["count"]

        aggregate_stats["timestamp"]["std"] = np.sqrt(((meta_stats["timestamp"]["std"]**2 + (meta_stats["timestamp"]["mean"] - (meta_stats["timestamp"]["mean"] * meta_stats["timestamp"]["count"]).sum(axis=0) / meta_stats["timestamp"]["count"].sum(axis=0))**2) * meta_stats["timestamp"]["count"]).sum(axis=0) / meta_stats["timestamp"]["count"].sum(axis=0))
        aggregate_stats["frame_index"]["std"] = np.sqrt(((meta_stats["frame_index"]["std"]**2 + (meta_stats["frame_index"]["mean"] - (meta_stats["frame_index"]["mean"] * meta_stats["frame_index"]["count"]).sum(axis=0) / meta_stats["frame_index"]["count"].sum(axis=0))**2) * meta_stats["frame_index"]["count"]).sum(axis=0) / meta_stats["frame_index"]["count"].sum(axis=0))
        aggregate_stats["episode_index"]["std"] = np.sqrt(((meta_stats["episode_index"]["std"]**2 + (meta_stats["episode_index"]["mean"] - (meta_stats["episode_index"]["mean"] * meta_stats["episode_index"]["count"]).sum(axis=0) / meta_stats["episode_index"]["count"].sum(axis=0))**2) * meta_stats["episode_index"]["count"]).sum(axis=0) / meta_stats["episode_index"]["count"].sum(axis=0))
        aggregate_stats["index"]["std"] = np.sqrt(((meta_stats["index"]["std"]**2 + (meta_stats["index"]["mean"] - (meta_stats["index"]["mean"] * meta_stats["index"]["count"]).sum(axis=0) / meta_stats["index"]["count"].sum(axis=0))**2) * meta_stats["index"]["count"]).sum(axis=0) / meta_stats["index"]["count"].sum(axis=0))
        aggregate_stats["task_index"]["std"] = np.sqrt(((meta_stats["task_index"]["std"]**2 + (meta_stats["task_index"]["mean"] - (meta_stats["task_index"]["mean"] * meta_stats["task_index"]["count"]).sum(axis=0) / meta_stats["task_index"]["count"].sum(axis=0))**2) * meta_stats["task_index"]["count"]).sum(axis=0) / meta_stats["task_index"]["count"].sum(axis=0))

        aggregate_stats["timestamp"]["q01"] = np.sum(meta_stats["timestamp"]["q01"] * meta_stats["timestamp"]["count"]) / aggregate_stats["timestamp"]["count"]
        aggregate_stats["timestamp"]["q10"] = np.sum(meta_stats["timestamp"]["q10"] * meta_stats["timestamp"]["count"]) / aggregate_stats["timestamp"]["count"]
        aggregate_stats["timestamp"]["q50"] = np.sum(meta_stats["timestamp"]["q50"] * meta_stats["timestamp"]["count"]) / aggregate_stats["timestamp"]["count"]
        aggregate_stats["timestamp"]["q90"] = np.sum(meta_stats["timestamp"]["q90"] * meta_stats["timestamp"]["count"]) / aggregate_stats["timestamp"]["count"]
        aggregate_stats["timestamp"]["q99"] = np.sum(meta_stats["timestamp"]["q99"] * meta_stats["timestamp"]["count"]) / aggregate_stats["timestamp"]["count"]

        aggregate_stats["frame_index"]["q01"] = np.sum(meta_stats["frame_index"]["q01"] * meta_stats["frame_index"]["count"]) / aggregate_stats["frame_index"]["count"]
        aggregate_stats["frame_index"]["q10"] = np.sum(meta_stats["frame_index"]["q10"] * meta_stats["frame_index"]["count"]) / aggregate_stats["frame_index"]["count"]
        aggregate_stats["frame_index"]["q50"] = np.sum(meta_stats["frame_index"]["q50"] * meta_stats["frame_index"]["count"]) / aggregate_stats["frame_index"]["count"]
        aggregate_stats["frame_index"]["q90"] = np.sum(meta_stats["frame_index"]["q90"] * meta_stats["frame_index"]["count"]) / aggregate_stats["frame_index"]["count"]
        aggregate_stats["frame_index"]["q99"] = np.sum(meta_stats["frame_index"]["q99"] * meta_stats["frame_index"]["count"]) / aggregate_stats["frame_index"]["count"]

        aggregate_stats["episode_index"]["q01"] = np.sum(meta_stats["episode_index"]["q01"] * meta_stats["episode_index"]["count"]) / aggregate_stats["episode_index"]["count"]
        aggregate_stats["episode_index"]["q10"] = np.sum(meta_stats["episode_index"]["q10"] * meta_stats["episode_index"]["count"]) / aggregate_stats["episode_index"]["count"]
        aggregate_stats["episode_index"]["q50"] = np.sum(meta_stats["episode_index"]["q50"] * meta_stats["episode_index"]["count"]) / aggregate_stats["episode_index"]["count"]
        aggregate_stats["episode_index"]["q90"] = np.sum(meta_stats["episode_index"]["q90"] * meta_stats["episode_index"]["count"]) / aggregate_stats["episode_index"]["count"]
        aggregate_stats["episode_index"]["q99"] = np.sum(meta_stats["episode_index"]["q99"] * meta_stats["episode_index"]["count"]) / aggregate_stats["episode_index"]["count"]

        aggregate_stats["index"]["q01"] = np.sum(meta_stats["index"]["q01"] * meta_stats["index"]["count"]) / aggregate_stats["index"]["count"]
        aggregate_stats["index"]["q10"] = np.sum(meta_stats["index"]["q10"] * meta_stats["index"]["count"]) / aggregate_stats["index"]["count"]
        aggregate_stats["index"]["q50"] = np.sum(meta_stats["index"]["q50"] * meta_stats["index"]["count"]) / aggregate_stats["index"]["count"]
        aggregate_stats["index"]["q90"] = np.sum(meta_stats["index"]["q90"] * meta_stats["index"]["count"]) / aggregate_stats["index"]["count"]
        aggregate_stats["index"]["q99"] = np.sum(meta_stats["index"]["q99"] * meta_stats["index"]["count"]) / aggregate_stats["index"]["count"]

        aggregate_stats["task_index"]["q01"] = np.sum(meta_stats["task_index"]["q01"] * meta_stats["task_index"]["count"]) / aggregate_stats["task_index"]["count"]
        aggregate_stats["task_index"]["q10"] = np.sum(meta_stats["task_index"]["q10"] * meta_stats["task_index"]["count"]) / aggregate_stats["task_index"]["count"]
        aggregate_stats["task_index"]["q50"] = np.sum(meta_stats["task_index"]["q50"] * meta_stats["task_index"]["count"]) / aggregate_stats["task_index"]["count"]
        aggregate_stats["task_index"]["q90"] = np.sum(meta_stats["task_index"]["q90"] * meta_stats["task_index"]["count"]) / aggregate_stats["task_index"]["count"]
        aggregate_stats["task_index"]["q99"] = np.sum(meta_stats["task_index"]["q99"] * meta_stats["task_index"]["count"]) / aggregate_stats["task_index"]["count"]

        aggregate_stats["action"] = {}
        aggregate_stats["observation.state"] = {}

        aggregate_stats["action"]["min"] = np.min(meta_stats["action"]["min"], axis=0)
        aggregate_stats["action"]["max"] = np.max(meta_stats["action"]["min"], axis=0)
        aggregate_stats["observation.state"]["min"] = np.min(meta_stats["observation.state"]["min"], axis=0)
        aggregate_stats["observation.state"]["max"] = np.max(meta_stats["observation.state"]["min"], axis=0)

        aggregate_stats["action"]["count"] = np.sum(meta_stats["action"]["count"])
        aggregate_stats["observation.state"]["count"] = np.sum(meta_stats["observation.state"]["count"])

        aggregate_stats["action"]["mean"] = np.sum(meta_stats["action"]["mean"] * meta_stats["action"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["action"]["count"]
        aggregate_stats["observation.state"]["mean"] = np.sum(meta_stats["observation.state"]["mean"] * meta_stats["observation.state"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["observation.state"]["count"]

        aggregate_stats["action"]["std"] = np.sqrt(np.sum(((meta_stats["action"]["std"]**2 + (meta_stats["action"]["mean"] - aggregate_stats["action"]["mean"])**2) * meta_stats["action"]["count"].reshape(-1, 1)), axis=0) / aggregate_stats["action"]["count"])
        aggregate_stats["observation.state"]["std"] = np.sqrt(np.sum(((meta_stats["observation.state"]["std"]**2 + (meta_stats["observation.state"]["mean"] - aggregate_stats["observation.state"]["mean"])**2) * meta_stats["observation.state"]["count"].reshape(-1, 1)), axis=0) / aggregate_stats["observation.state"]["count"])

        aggregate_stats["action"]["q01"] = np.sum(meta_stats["action"]["q01"] * meta_stats["action"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["action"]["count"]
        aggregate_stats["action"]["q10"] = np.sum(meta_stats["action"]["q10"] * meta_stats["action"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["action"]["count"]
        aggregate_stats["action"]["q50"] = np.sum(meta_stats["action"]["q50"] * meta_stats["action"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["action"]["count"]
        aggregate_stats["action"]["q90"] = np.sum(meta_stats["action"]["q90"] * meta_stats["action"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["action"]["count"]
        aggregate_stats["action"]["q99"] = np.sum(meta_stats["action"]["q99"] * meta_stats["action"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["action"]["count"]

        aggregate_stats["observation.state"]["q01"] = np.sum(meta_stats["observation.state"]["q01"] * meta_stats["observation.state"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["observation.state"]["count"]
        aggregate_stats["observation.state"]["q10"] = np.sum(meta_stats["observation.state"]["q10"] * meta_stats["observation.state"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["observation.state"]["count"]
        aggregate_stats["observation.state"]["q50"] = np.sum(meta_stats["observation.state"]["q50"] * meta_stats["observation.state"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["observation.state"]["count"]
        aggregate_stats["observation.state"]["q90"] = np.sum(meta_stats["observation.state"]["q90"] * meta_stats["observation.state"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["observation.state"]["count"]
        aggregate_stats["observation.state"]["q99"] = np.sum(meta_stats["observation.state"]["q99"] * meta_stats["observation.state"]["count"].reshape(-1, 1), axis=0) / aggregate_stats["observation.state"]["count"]

        for video_key in self.observation_keys:
            aggregate_stats[f"{video_key}"] = {}
            aggregate_stats[f"{video_key}"]["min"] = np.min(meta_stats[f"{video_key}"]["min"], axis=0)
            aggregate_stats[f"{video_key}"]["max"] = np.max(meta_stats[f"{video_key}"]["max"], axis=0)
            aggregate_stats[f"{video_key}"]["count"] = np.sum(meta_stats[f"{video_key}"]["count"])
            aggregate_stats[f"{video_key}"]["mean"] = np.sum(meta_stats[f"{video_key}"]["mean"] * meta_stats[f"{video_key}"]["count"].reshape(-1, 1), axis=0) / aggregate_stats[f"{video_key}"]["count"]
            aggregate_stats[f"{video_key}"]["std"] = np.sqrt(np.sum(((meta_stats[f"{video_key}"]["std"]**2 + (meta_stats[f"{video_key}"]["mean"] - aggregate_stats[f"{video_key}"]["mean"])**2) * meta_stats[f"{video_key}"]["count"].reshape(-1, 1)), axis=0) / aggregate_stats[f"{video_key}"]["count"])
            aggregate_stats[f"{video_key}"]["q01"] = np.sum(meta_stats[f"{video_key}"]["q01"] * meta_stats[f"{video_key}"]["count"].reshape(-1, 1), axis=0) / aggregate_stats[f"{video_key}"]["count"]
            aggregate_stats[f"{video_key}"]["q10"] = np.sum(meta_stats[f"{video_key}"]["q10"] * meta_stats[f"{video_key}"]["count"].reshape(-1, 1), axis=0) / aggregate_stats[f"{video_key}"]["count"]
            aggregate_stats[f"{video_key}"]["q50"] = np.sum(meta_stats[f"{video_key}"]["q50"] * meta_stats[f"{video_key}"]["count"].reshape(-1, 1), axis=0) / aggregate_stats[f"{video_key}"]["count"]
            aggregate_stats[f"{video_key}"]["q90"] = np.sum(meta_stats[f"{video_key}"]["q90"] * meta_stats[f"{video_key}"]["count"].reshape(-1, 1), axis=0) / aggregate_stats[f"{video_key}"]["count"]
            aggregate_stats[f"{video_key}"]["q99"] = np.sum(meta_stats[f"{video_key}"]["q99"] * meta_stats[f"{video_key}"]["count"].reshape(-1, 1), axis=0) / aggregate_stats[f"{video_key}"]["count"]

        aggregate_stats = self.convert_numpy_to_python(aggregate_stats)

        data = self._build_json_data(aggregate_stats)
        output_path = self.dataset_path / "meta" / "stats.json"
        old_path = self.dataset_path / "meta" / "stats.json"

        if os.path.exists(old_path):
            os.remove(old_path)

        self.json_editor.save(output_path, data)



    def _build_json_data(self, aggregate_stats):
        stats = {}
        for video_key in self.observation_keys:
            stats[f"{video_key}"] = {}
            stats[f"{video_key}"]["min"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["min"]]
            stats[f"{video_key}"]["max"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["max"]]
            stats[f"{video_key}"]["mean"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["mean"]]
            stats[f"{video_key}"]["std"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["std"]]
            stats[f"{video_key}"]["count"] = [aggregate_stats[f"{video_key}"]["count"]]
            stats[f"{video_key}"]["q01"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["q01"]]
            stats[f"{video_key}"]["q10"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["q10"]]
            stats[f"{video_key}"]["q50"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["q50"]]
            stats[f"{video_key}"]["q90"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["q90"]]
            stats[f"{video_key}"]["q99"] = [[[value]] for value in aggregate_stats[f"{video_key}"]["q99"]]

        stats["observation.state"] = {}
        stats["observation.state"]["min"] = aggregate_stats["observation.state"]["min"]
        stats["observation.state"]["max"] = aggregate_stats["observation.state"]["max"]
        stats["observation.state"]["mean"] = aggregate_stats["observation.state"]["mean"]
        stats["observation.state"]["std"] = aggregate_stats["observation.state"]["std"]
        stats["observation.state"]["count"] = [aggregate_stats["observation.state"]["count"]]
        stats["observation.state"]["q01"] = aggregate_stats["observation.state"]["q01"]
        stats["observation.state"]["q10"] = aggregate_stats["observation.state"]["q10"]
        stats["observation.state"]["q50"] = aggregate_stats["observation.state"]["q50"]
        stats["observation.state"]["q90"] = aggregate_stats["observation.state"]["q90"]
        stats["observation.state"]["q99"] = aggregate_stats["observation.state"]["q99"]

        stats["action"] = {}
        stats["action"]["min"] = aggregate_stats["action"]["min"]
        stats["action"]["max"] = aggregate_stats["action"]["max"]
        stats["action"]["mean"] = aggregate_stats["action"]["mean"]
        stats["action"]["std"] = aggregate_stats["action"]["std"]
        stats["action"]["count"] = [aggregate_stats["action"]["count"]]
        stats["action"]["q01"] = aggregate_stats["action"]["q01"]
        stats["action"]["q10"] = aggregate_stats["action"]["q10"]
        stats["action"]["q50"] = aggregate_stats["action"]["q50"]
        stats["action"]["q90"] = aggregate_stats["action"]["q90"]
        stats["action"]["q99"] = aggregate_stats["action"]["q99"]

        stats["timestamp"] = {}
        stats["timestamp"]["min"] = [aggregate_stats["timestamp"]["min"]]
        stats["timestamp"]["max"] = [aggregate_stats["timestamp"]["max"]]
        stats["timestamp"]["mean"] = [aggregate_stats["timestamp"]["mean"]]
        stats["timestamp"]["std"] = [aggregate_stats["timestamp"]["std"]]
        stats["timestamp"]["count"] = [aggregate_stats["timestamp"]["count"]]
        stats["timestamp"]["q01"] = [aggregate_stats["timestamp"]["q01"]]
        stats["timestamp"]["q10"] = [aggregate_stats["timestamp"]["q10"]]
        stats["timestamp"]["q50"] = [aggregate_stats["timestamp"]["q50"]]
        stats["timestamp"]["q90"] = [aggregate_stats["timestamp"]["q90"]]
        stats["timestamp"]["q99"] = [aggregate_stats["timestamp"]["q99"]]

        stats["frame_index"] = {}
        stats["frame_index"]["min"] = [aggregate_stats["frame_index"]["min"]]
        stats["frame_index"]["max"] = [aggregate_stats["frame_index"]["max"]]
        stats["frame_index"]["mean"] = [aggregate_stats["frame_index"]["mean"]]
        stats["frame_index"]["std"] = [aggregate_stats["frame_index"]["std"]]
        stats["frame_index"]["count"] = [aggregate_stats["frame_index"]["count"]]
        stats["frame_index"]["q01"] = [aggregate_stats["frame_index"]["q01"]]
        stats["frame_index"]["q10"] = [aggregate_stats["frame_index"]["q10"]]
        stats["frame_index"]["q50"] = [aggregate_stats["frame_index"]["q50"]]
        stats["frame_index"]["q90"] = [aggregate_stats["frame_index"]["q90"]]
        stats["frame_index"]["q99"] = [aggregate_stats["frame_index"]["q99"]]

        stats["task_index"] = {}
        stats["task_index"]["min"] = [aggregate_stats["task_index"]["min"]]
        stats["task_index"]["max"] = [aggregate_stats["task_index"]["max"]]
        stats["task_index"]["mean"] = [aggregate_stats["task_index"]["mean"]]
        stats["task_index"]["std"] = [aggregate_stats["task_index"]["std"]]
        stats["task_index"]["count"] = [aggregate_stats["task_index"]["count"]]
        stats["task_index"]["q01"] = [aggregate_stats["task_index"]["q01"]]
        stats["task_index"]["q10"] = [aggregate_stats["task_index"]["q10"]]
        stats["task_index"]["q50"] = [aggregate_stats["task_index"]["q50"]]
        stats["task_index"]["q90"] = [aggregate_stats["task_index"]["q90"]]
        stats["task_index"]["q99"] = [aggregate_stats["task_index"]["q99"]]

        stats["index"] = {}
        stats["index"]["min"] = [aggregate_stats["index"]["min"]]
        stats["index"]["max"] = [aggregate_stats["index"]["max"]]
        stats["index"]["mean"] = [aggregate_stats["index"]["mean"]]
        stats["index"]["std"] = [aggregate_stats["index"]["std"]]
        stats["index"]["count"] = [aggregate_stats["index"]["count"]]
        stats["index"]["q01"] = [aggregate_stats["index"]["q01"]]
        stats["index"]["q10"] = [aggregate_stats["index"]["q10"]]
        stats["index"]["q50"] = [aggregate_stats["index"]["q50"]]
        stats["index"]["q90"] = [aggregate_stats["index"]["q90"]]
        stats["index"]["q99"] = [aggregate_stats["index"]["q99"]]

        stats["episode_index"] = {}
        stats["episode_index"]["min"] = [aggregate_stats["episode_index"]["min"]]
        stats["episode_index"]["max"] = [aggregate_stats["episode_index"]["max"]]
        stats["episode_index"]["mean"] = [aggregate_stats["episode_index"]["mean"]]
        stats["episode_index"]["std"] = [aggregate_stats["episode_index"]["std"]]
        stats["episode_index"]["count"] = [aggregate_stats["episode_index"]["count"]]
        stats["episode_index"]["q01"] = [aggregate_stats["episode_index"]["q01"]]
        stats["episode_index"]["q10"] = [aggregate_stats["episode_index"]["q10"]]
        stats["episode_index"]["q50"] = [aggregate_stats["episode_index"]["q50"]]
        stats["episode_index"]["q90"] = [aggregate_stats["episode_index"]["q90"]]
        stats["episode_index"]["q99"] = [aggregate_stats["episode_index"]["q99"]]

        return stats

    def reprocess(self):
        start = time.time()
        self.mcap_to_mp4()
        print("mcap_to_mp4 完成， 耗时：", time.time() - start)

        start = time.time()
        self.update_info()
        print("update_info 完成， 耗时：", time.time() - start)

        start = time.time()
        self.get_dataset_stats()
        print("get_dataset_stats 完成， 耗时：", time.time() - start)

        start = time.time()
        self.get_dataset_videos()
        print("get_dataset_videos 完成， 耗时：", time.time() - start)

        start = time.time()
        self.get_cam_stats()
        print("get_cam_stats 完成， 耗时：", time.time() - start)

        start = time.time()
        self.save_meta_parquet()
        print("save_meta_parquet 完成， 耗时：", time.time() - start)

        start = time.time()
        self.save_meta_stats()
        print("save_meta_stats 完成， 耗时：", time.time() - start)

def main():
    parser = argparse.ArgumentParser(
        description='ReProcessing',
        epilog='示例'
    )
    parser.add_argument('-p', '--dataset_path', type=Path, required=True, help='数据集路径')
    parser.add_argument('--use_nvenc', action='store_true', default=False, help='使用硬件编码')
    args = parser.parse_args()
    dataset_path = args.dataset_path
    use_nvenc = args.use_nvenc
    reprocessing = ReProcessing(dataset_path, use_nvenc)

    start = time.time()
    reprocessing.reprocess()


    print(f"\n✅ Reprocessing完成!总耗时：", time.time() - start)


if __name__ == "__main__":
    main()
