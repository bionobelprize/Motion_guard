# 新版客户端，兼容 main.py FastAPI 服务参数和响应格式
import os
import requests
import zipfile
from io import BytesIO

CHATTTS_SERVICE_HOST = os.environ.get("CHATTTS_SERVICE_HOST", "localhost")
CHATTTS_SERVICE_PORT = os.environ.get("CHATTTS_SERVICE_PORT", "8000")
CHATTTS_URL = f"http://{CHATTTS_SERVICE_HOST}:{CHATTTS_SERVICE_PORT}/generate_voice"

def get_body(stream_mode):
    return {
        "text": [
            "四川美食确实以辣闻名，但也有不辣的选择。",
            "比如甜水面、赖汤圆、蛋烘糕、叶儿粑等，这些小吃口味温和，甜而不腻，也很受欢迎。",
        ],
        "stream": stream_mode,
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

def save_zip_response(response, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(BytesIO(response.content), "r") as zip_ref:
        zip_ref.extractall(out_dir)
    print(f"Extracted files to {out_dir}")

def save_stream_response(response, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    import numpy as np
    from scipy.io import wavfile
    # 收集所有PCM块
    audio_chunks = []
    for chunk in response.iter_content(chunk_size=8192):
        arr = np.frombuffer(chunk, dtype=np.int16)
        if arr.size > 0:
            audio_chunks.append(arr)
    if audio_chunks:
        audio_all = np.concatenate(audio_chunks)
    else:
        audio_all = np.array([], dtype=np.int16)
    out_path = os.path.join(out_dir, "audio_stream.wav")
    # 保存为WAV文件，采样率假定为24000（与服务端一致）
    wavfile.write(out_path, 24000, audio_all)
    print(f"Saved stream audio to {out_path}")


def test_api(stream_mode):
    body = get_body(stream_mode)
    print(f"Testing stream={stream_mode}")
    response = requests.post(CHATTTS_URL, json=body, stream=stream_mode)
    response.raise_for_status()
    out_dir = f"./output_stream_{stream_mode}/"
    #print("Response status:", response.status_code)
    #print("Response headers:", response.headers)
    if response.headers.get("Content-Type", "").startswith("application/zip") or response.headers.get("Content-Type", "").startswith("application/octet-stream"):
        if stream_mode:
            save_stream_response(response, out_dir)
        else:
            save_zip_response(response, out_dir)
    else:
        print("Unexpected response type:", response.headers.get("Content-Type"))

if __name__ == "__main__":
    #test_api(stream_mode=False)
    test_api(stream_mode=True)