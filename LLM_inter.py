import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable
import logging
import time
import gc
import tkinter as tk
from tkinter import scrolledtext, messagebox
import queue
import threading
from threading import Thread
from flask import Flask, request, jsonify
import logging
# 新增：导入MCP AI客户端
from mcp_client_servers import MCPClientWrapper
from pydub import AudioSegment
from pydub.playback import play
from playsound import playsound
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LLMInterventionServer")

# 初始化AI客户端（全局只初始化一次）
mcp_ai_client = MCPClientWrapper()

# 用于主线程和GUI线程通信
gui_result_queue = queue.Queue()

def play_voice(text):
    import requests
    import zipfile
    import os
    from io import BytesIO
    import tempfile
    print(f"准备播放语音: {text}")
    chattts_service_host = os.environ.get("CHATTTS_SERVICE_HOST", "localhost")
    chattts_service_port = os.environ.get("CHATTTS_SERVICE_PORT", "8000")
    CHATTTS_URL = f"http://{chattts_service_host}:{chattts_service_port}/generate_voice"

    body = {
        "text": [text],
        "stream": False,
        "lang": None,
        "skip_refine_text": True,
        "refine_text_only": False,
        "use_decoder": True,
        "do_text_normalization": True,
        "do_homophone_replacement": False,
        "params_refine_text": {
            "prompt": "",
            "top_P": 0.1,
            "top_K": 1,
            "temperature": 0.01,
            "repetition_penalty": 1,
            "max_new_token": 384,
            "min_new_token": 0,
            "show_tqdm": False,
            "ensure_non_empty": True,
            "stream_batch": 24,
        },
        "params_infer_code": {
            "prompt": "[speed_5]",
            "top_P": 0.1,
            "top_K": 1,
            "temperature": 0.01,
            "repetition_penalty": 1.05,
            "max_new_token": 2048,
            "min_new_token": 0,
            "show_tqdm": False,
            "ensure_non_empty": True,
            "stream_batch": True,
            "spk_emb": None,
        }
    }
    try:
        response = requests.post(CHATTTS_URL, json=body)
        response.raise_for_status()
        with zipfile.ZipFile(BytesIO(response.content), "r") as zip_ref:
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_ref.extractall(tmpdir)
                # 找到第一个音频文件（优先mp3，其次wav）
                audio_files = [f for f in os.listdir(tmpdir) if f.endswith(".mp3") or f.endswith(".wav")]
                if audio_files:
                    audio_path = os.path.join(tmpdir, audio_files[0])
                    try:
                        if audio_path.endswith(".mp3"):
                            audio = AudioSegment.from_mp3(audio_path)
                            play(audio)
                        else:
                            playsound(audio_path)
                    except Exception as e:
                        print(f"音频播放失败: {e}")
                        try:
                            if audio_path.endswith(".mp3"):
                                audio = AudioSegment.from_mp3(audio_path)
                                play(audio)
                            else:
                                audio = AudioSegment.from_wav(audio_path)
                                play(audio)
                        except Exception as e2:
                            print(f"pydub 播放也失败: {e2}")
    except Exception as e:
        print(f"语音播放失败: {e}")


def run_intervention_gui(alert_data):
    """弹出Tkinter窗口，收集用户输入，AI介入，返回结果"""
    result = {}
    root = tk.Tk()
    root.title("EmoGuard - 情感关怀助手")
    root.geometry("600x400")
    root.configure(bg='#f0f0f0')

    # 标题
    title_label = tk.Label(
        root, 
        text="🤖 EmoGuard 情感关怀对话", 
        font=("Arial", 16, "bold"),
        bg='#f0f0f0',
        fg='#2c3e50'
    )
    title_label.pack(pady=10)

    # 对话显示区域
    text_widget = scrolledtext.ScrolledText(
        root,
        wrap=tk.WORD,
        width=70,
        height=15,
        font=("Arial", 11),
        bg='#ffffff',
        fg='#2c3e50'
    )
    text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
    text_widget.config(state=tk.NORMAL)
    # 初始提示
    initial_message = "您好，我注意到您的心率异常（{}），请问您现在感觉如何？".format(alert_data.get('heart_rate', '未知'))
    text_widget.insert(tk.END, f"情感助手: {initial_message}\n\n")
    text_widget.config(state=tk.DISABLED)

    # 输入区域
    input_frame = tk.Frame(root, bg='#f0f0f0')
    input_frame.pack(fill=tk.X, padx=10, pady=10)
    input_label = tk.Label(
        input_frame,
        text="您的回复:",
        font=("Arial", 10),
        bg='#f0f0f0'
    )
    input_label.pack(anchor=tk.W)
    entry_widget = tk.Entry(
        input_frame,
        font=("Arial", 12),
        width=50
    )
    entry_widget.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

    # 新增：AI对话循环控制变量
    continue_dialog = True

    def on_send(event=None):
        nonlocal continue_dialog
        user_input = entry_widget.get().strip()
        if user_input:
            text_widget.config(state=tk.NORMAL)
            text_widget.insert(tk.END, f"您: {user_input}\n\n")
            text_widget.config(state=tk.DISABLED)
            entry_widget.delete(0, tk.END)
            # AI介入：调用MCP工具处理用户输入
            ai_result = mcp_ai_client.process_user_input(user_input, alert_data)
            ai_dict = ai_result.get("ai_response", {})
            ai_response = ai_dict['result_str']
            text_widget.config(state=tk.NORMAL)
            text_widget.insert(tk.END, f"情感助手: {ai_response}\n\n")
            text_widget.insert(tk.END, f"完整数据反馈: {ai_dict}\n\n")
            if ai_dict['tool_results']:
                for tool_res in ai_dict['tool_results']:
                    if tool_res['tool_name'] == 'email_sender__send_fixed_email':
                        text_widget.insert(tk.END, f"（系统已尝试发送邮件，结果：{tool_res['result']}）\n\n")
                    elif tool_res['tool_name'] == 'email_sender__psychological_counseling_decision':
                        text_widget.insert(tk.END, f"（系统心理疏导建议：{tool_res['result']}）\n\n")
                        # 开始进行心理疏导对话
                        from emotional_consulting import EmotionalConsultingSystem
                        user_info = {
                            'name': alert_data.get('user_name', '用户'),
                            'age': alert_data.get('user_age', '未提供'),
                            'topic': '心理疏导',
                            'session_count': 1
                        }
                        consulting = EmotionalConsultingSystem(user_info)
                        text_widget.config(state=tk.NORMAL)
                        text_widget.insert(tk.END, f"\n【心理疏导对话已开启，您可以与李老师交流，输入'结束'或'终止'可随时退出】\n\n")
                        text_widget.config(state=tk.DISABLED)
                        # 事件驱动循环
                        def on_psy_send(event=None):
                            user_input_psy = entry_widget.get().strip()
                            if user_input_psy:
                                text_widget.config(state=tk.NORMAL)
                                text_widget.insert(tk.END, f"您: {user_input_psy}\n\n")
                                text_widget.config(state=tk.DISABLED)
                                entry_widget.delete(0, tk.END)
                                ai_psy_response = consulting.consult(user_input_psy)
                                text_widget.config(state=tk.NORMAL)
                                text_widget.insert(tk.END, f"李老师: {ai_psy_response}\n\n")
                                #在此启动音频播放线程
                                Thread(target=play_voice, args=(ai_psy_response,), daemon=True).start()
                                text_widget.config(state=tk.DISABLED)
                                text_widget.see(tk.END)
                                if "结束" in user_input_psy or "终止" in user_input_psy or "结束" in ai_psy_response or "终止" in ai_psy_response:
                                    text_widget.config(state=tk.NORMAL)
                                    text_widget.insert(tk.END, "【心理疏导对话已结束】\n\n")
                                    text_widget.config(state=tk.NORMAL)
                                    text_widget.insert(tk.END, "\n" + "="*50 + "\n")
                                    progress = consulting.get_session_progress()
                                    text_widget.insert(tk.END, f"【咨询总结】: {progress}\n")
                                    save_result = consulting.save_session_log()
                                    text_widget.insert(tk.END, f"【会话记录】: {save_result}\n")
                                    text_widget.config(state=tk.DISABLED)
                                    text_widget.config(state=tk.DISABLED)
                                    entry_widget.unbind('<Return>')
                                    psy_send_button.config(state=tk.DISABLED)
                        # 绑定新的回车事件
                        entry_widget.unbind('<Return>')
                        entry_widget.bind('<Return>', on_psy_send)
                        psy_send_button = tk.Button(
                            input_frame,
                            text="发送（心理疏导）",
                            command=on_psy_send,
                            bg='#27ae60',
                            fg='white',
                            font=("Arial", 10, "bold")
                        )
                        psy_send_button.pack(side=tk.RIGHT)
                        # 结束后可保存日志或做后续处理
                        # consulting.save_session_log()

            text_widget.see(tk.END)
            text_widget.config(state=tk.DISABLED)
            # 这里可以根据ai_response内容判断是否需要继续对话或调用工具
            # 示例：如果AI建议终止，则结束对话
            if "终止" in ai_response or "结束" in ai_response:
                continue_dialog = False
                result['user_input'] = user_input
                result['ai_response'] = ai_response
                root.quit()
                root.destroy()
            # 如果AI建议发送邮件或心理疏导，可在此处扩展相关逻辑
            # 否则继续等待用户输入

    entry_widget.bind('<Return>', on_send)
    send_button = tk.Button(
        input_frame,
        text="发送",
        command=on_send,
        bg='#3498db',
        fg='white',
        font=("Arial", 10, "bold")
    )
    send_button.pack(side=tk.RIGHT)

    def on_close():
        if messagebox.askokcancel("退出", "确定要结束这次关怀对话吗？"):
            result['user_input'] = None
            root.quit()
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    gui_result_queue.put(result)

def start_gui_thread(alert_data):
    gui_thread = threading.Thread(target=run_intervention_gui, args=(alert_data,), daemon=True)
    gui_thread.start()
    gui_thread.join()
    # 获取结果
    if not gui_result_queue.empty():
        return gui_result_queue.get()
    return {"user_input": None}

@app.route('/intervene', methods=['POST'])
def intervene():
    alert_data = request.json or {}
    logger.info(f"收到干预请求: {alert_data}")
    result = start_gui_thread(alert_data)
    logger.info(f"用户干预结果: {result}")
    return jsonify(result)

if __name__ == "__main__":
    logger.info("LLM_inter.py 以独立服务模式启动，监听 http://127.0.0.1:5005/intervene ...")
    app.run(host="127.0.0.1", port=5005, debug=False)

