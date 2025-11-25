import os
import requests
import pyaudio
import threading
import time
from queue import Queue
import numpy as np
import io
import wave
import json

# 配置参数
CHATTTS_SERVICE_HOST = os.environ.get("CHATTTS_SERVICE_HOST", "localhost")
CHATTTS_SERVICE_PORT = os.environ.get("CHATTTS_SERVICE_PORT", "8000")
CHATTTS_URL = f"http://{CHATTTS_SERVICE_HOST}:{CHATTTS_SERVICE_PORT}/generate_voice"

# 音频参数
SAMPLE_RATE = 24000
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

class AudioStreamPlayer:
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.audio_queue = Queue()
        self.is_playing = False
        self.playback_thread = None
        self.current_audio_data = None
        self.audio_position = 0
        
    def start_playback(self):
        """启动音频播放"""
        if self.stream is None:
            self.stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                output=True,
                frames_per_buffer=CHUNK_SIZE
            )
        
        self.is_playing = True
        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=self._playback_loop)
            self.playback_thread.daemon = True
            self.playback_thread.start()
    
    def stop_playback(self):
        """停止音频播放"""
        self.is_playing = False
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
    
    def set_audio_data(self, audio_data):
        """设置完整的音频数据"""
        self.current_audio_data = audio_data
        self.audio_position = 0
    
    def _playback_loop(self):
        """播放循环 - 播放完整的音频数据"""
        while self.is_playing:
            if self.current_audio_data is not None and self.audio_position < len(self.current_audio_data):
                # 计算剩余数据量
                remaining = len(self.current_audio_data) - self.audio_position
                chunk_size = min(CHUNK_SIZE, remaining)
                
                # 获取当前块
                chunk = self.current_audio_data[self.audio_position:self.audio_position + chunk_size]
                self.audio_position += chunk_size
                
                # 播放音频
                if self.stream is not None:
                    self.stream.write(chunk.tobytes())
                
                # 如果播放完毕，重置
                if self.audio_position >= len(self.current_audio_data):
                    self.current_audio_data = None
                    self.audio_position = 0
            else:
                # 没有数据时短暂休眠
                time.sleep(0.01)
    
    def cleanup(self):
        """清理资源"""
        self.stop_playback()
        if self.audio:
            self.audio.terminate()

class TTSStreamClient:
    def __init__(self):
        self.player = AudioStreamPlayer()
        self.is_running = False
        
    def get_tts_request_body(self, text):
        """生成TTS请求体"""
        return {
            "text": [text],
            "stream": True,
            "lang": None,
            "skip_refine_text": True,
            "refine_text_only": False,
            "use_decoder": True,
            "do_text_normalization": True,
            "do_homophone_replacement": False,
            "params_refine_text": {
                "prompt": "",
                "top_P": 0.7,
                "top_K": 20,
                "temperature": 0.01,
                "repetition_penalty": 1,
                "max_new_token": 384,
                "min_new_token": 0,
                "show_tqdm": True,
                "ensure_non_empty": True,
                "stream_batch": 24,
            },
            "params_infer_code": {
                "prompt": "[speed_2]",
                "top_P": 0.1,
                "top_K": 20,
                "temperature": 0.01,
                "repetition_penalty": 1.05,
                "max_new_token": 2048,
                "min_new_token": 0,
                "show_tqdm": True,
                "ensure_non_empty": True,
                "stream_batch": True,
                "spk_emb": None,
                "manual_seed": 12345678,
            }
        }
    
    def process_stream_response(self, response):
        """处理流式响应并播放音频 - 收集完整音频后再播放"""
        print("开始接收音频流...")
        
        # 收集所有音频数据
        audio_chunks = []
        total_size = 0
        
        try:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk is not None and len(chunk) > 0:
                    audio_chunks.append(chunk)
                    total_size += len(chunk)
                    print(f"已接收 {total_size} 字节音频数据")
        
        except Exception as e:
            print(f"接收音频流时出错: {e}")
            return
        
        if total_size == 0:
            print("未接收到音频数据")
            return
        
        # 合并所有数据块
        full_audio_bytes = b''.join(audio_chunks)
        print(f"音频数据接收完成，总大小: {len(full_audio_bytes)} 字节")
        
        try:
            # 尝试解析为WAV文件
            if full_audio_bytes[:4] == b'RIFF':
                print("检测到WAV格式音频")
                # 使用wave模块解析WAV文件
                with io.BytesIO(full_audio_bytes) as wav_file:
                    with wave.open(wav_file, 'rb') as wav:
                        # 获取音频参数
                        channels = wav.getnchannels()
                        sample_width = wav.getsampwidth()
                        frame_rate = wav.getframerate()
                        n_frames = wav.getnframes()
                        
                        print(f"WAV参数: {channels}声道, {sample_width}字节/采样, {frame_rate}Hz, {n_frames}帧")
                        
                        # 读取所有帧数据
                        frames = wav.readframes(n_frames)
                        
                        # 根据采样宽度转换为numpy数组
                        if sample_width == 2:  # 16bit
                            audio_data = np.frombuffer(frames, dtype=np.int16)
                        elif sample_width == 4:  # 32bit
                            audio_data = np.frombuffer(frames, dtype=np.int32)
                        else:
                            # 默认按16bit处理
                            audio_data = np.frombuffer(frames, dtype=np.int16)
                        
            else:
                print("检测到原始PCM数据")
                # 直接作为PCM数据处理（16bit）
                audio_data = np.frombuffer(full_audio_bytes, dtype=np.int16)
            
            print(f"音频数据准备完成: {len(audio_data)} 采样点")
            
            # 设置音频数据并开始播放
            self.player.set_audio_data(audio_data)
            
            # 等待播放完成
            while self.player.current_audio_data is not None:
                time.sleep(0.1)
                
            print("音频播放完成")
            
        except Exception as e:
            print(f"处理音频数据时出错: {e}")
            # 尝试直接作为原始PCM数据处理
            try:
                print("尝试作为原始PCM数据处理...")
                audio_data = np.frombuffer(full_audio_bytes, dtype=np.int16)
                print(f"原始PCM数据: {len(audio_data)} 采样点")
                
                self.player.set_audio_data(audio_data)
                
                # 等待播放完成
                while self.player.current_audio_data is not None:
                    time.sleep(0.1)
                    
            except Exception as e2:
                print(f"处理原始PCM数据也失败: {e2}")
    
    def request_and_play(self, text):
        """请求TTS服务并播放音频"""
        try:
            body = self.get_tts_request_body(text)
            print(f"请求TTS服务: {text}")
            
            # 设置较长的超时时间
            response = requests.post(CHATTTS_URL, json=body, stream=True, timeout=60)
            response.raise_for_status()
            
            # 检查响应内容类型
            content_type = response.headers.get('Content-Type', '')
            content_length = response.headers.get('Content-Length', '未知')
            print(f"响应类型: {content_type}, 长度: {content_length}")
            
            # 处理流响应
            self.process_stream_response(response)
            
        except requests.exceptions.RequestException as e:
            print(f"请求TTS服务失败: {e}")
        except Exception as e:
            print(f"处理TTS请求时出错: {e}")
    
    def start_interactive_mode(self):
        """启动交互模式，用户可以输入文本"""
        self.is_running = True
        self.player.start_playback()
        
        print("TTS流媒体播放器已启动（交互模式）")
        print("输入要合成的文本（输入'quit'退出）：")
        
        try:
            while self.is_running:
                try:
                    text = input("> ").strip()
                    
                    if text.lower() == 'quit':
                        break
                    
                    if text:
                        # 直接在当前线程处理，避免并发问题
                        self.request_and_play(text)
                    else:
                        print("请输入有效文本")
                        
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"处理输入时出错: {e}")
                    
        except KeyboardInterrupt:
            print("\n接收到中断信号")
        finally:
            self.stop()
    
    def start_demo_mode(self):
        """启动演示模式，自动播放测试文本"""
        self.is_running = True
        self.player.start_playback()
        
        print("TTS流媒体播放器已启动（演示模式）")
        print("按Ctrl+C退出")
        
        try:
            test_texts = [
                "欢迎使用实时语音合成系统。",
                "这是一个流式音频播放演示。",
                "语音合成技术正在快速发展。",
                "感谢使用我们的服务。"
            ]
            
            while self.is_running:
                for text in test_texts:
                    if not self.is_running:
                        break
                    
                    print(f"\n合成文本: {text}")
                    self.request_and_play(text)
                    
                    # 等待播放完成
                    time.sleep(1)
                    
                if self.is_running:
                    time.sleep(2)
                    
        except KeyboardInterrupt:
            print("\n接收到中断信号")
        finally:
            self.stop()
    
    def stop(self):
        """停止服务"""
        self.is_running = False
        self.player.cleanup()
        print("TTS流媒体播放器已停止")

def main():
    # 检查依赖
    try:
        import pyaudio
    except ImportError:
        print("错误: 需要安装PyAudio库")
        print("请运行: pip install pyaudio")
        return
    
    try:
        import requests
    except ImportError:
        print("错误: 需要安装requests库")
        print("请运行: pip install requests")
        return
    
    client = TTSStreamClient()
    
    try:
        # 让用户选择模式
        print("请选择运行模式:")
        print("1. 交互模式（手动输入文本）")
        print("2. 演示模式（自动播放测试文本）")
        
        choice = input("请输入选择 (1 或 2): ").strip()
        
        if choice == "1":
            client.start_interactive_mode()
        elif choice == "2":
            client.start_demo_mode()
        else:
            print("无效选择，使用默认的交互模式")
            client.start_interactive_mode()
            
    except Exception as e:
        print(f"程序运行出错: {e}")
    finally:
        client.stop()

if __name__ == "__main__":
    main()