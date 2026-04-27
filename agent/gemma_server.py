"""
Gemma 4 E4B 서빙 스크립트.
vLLM으로 vision + tool calling + reasoning 활성화.

사용:
    python gemma_server.py
    # → http://localhost:8000 에서 OpenAI-compatible API 제공
"""
import subprocess
import sys


MODEL_ID = "google/gemma-4-E4B-it"
PORT = 8000


def start_server():
    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", MODEL_ID,
        "--port", str(PORT),
        "--enable-auto-tool-choice",
        "--reasoning-parser", "gemma4",
        "--tool-call-parser", "gemma4",
    ]
    print(f"Starting Gemma 4 server on port {PORT}...")
    subprocess.run(cmd)


if __name__ == "__main__":
    start_server()
