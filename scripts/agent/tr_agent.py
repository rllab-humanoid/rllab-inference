import base64
import mimetypes
import os
import re
import time
from pathlib import Path

import requests

DEFAULT_BACKEND = os.getenv("TR_AGENT_BACKEND", "server").lower()
DEFAULT_MODEL_ID = os.getenv("VLLM_MODEL", "google/gemma-4-26B-A4B-it")
DEFAULT_VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:30000/v1")
DEFAULT_REQUEST_TIMEOUT = float(os.getenv("TR_AGENT_TIMEOUT", "120"))
DEFAULT_MAX_MODEL_LEN = int(os.getenv("TR_AGENT_MAX_MODEL_LEN", "4096"))
DEFAULT_GPU_MEMORY_UTILIZATION = float(os.getenv("TR_AGENT_GPU_MEMORY_UTILIZATION", "0.6"))
DEFAULT_MAX_TOKENS = int(os.getenv("TR_AGENT_MAX_TOKENS", "256"))

prompts = {
    "A": """다음 이미지(모니터 화면)에 표시된 부품의 종류와 수량을 확인하여 아래 형식으로 답변해줘.
**규칙:**
1. **대상 부품:** 플랜지 너트, 기어 링, 스페이서 링, 육각 너트, 돔 너트 5 가지 종류 물체만 카운트할 것.
2. **수량 지정:** 이미지에서 확인되는 실제 수량을 기입하되, (n)은 1~5 사이의 숫자로 작성해줘. (만약 해당 부품이 없다면 0으로 표시)
3. **정확도:** 부품이 서로 겹쳐 있거나 화면 끝에 걸쳐 있어도 식별 가능하다면 수량에 포함해줘.
4. **출력 형식:** 아래 양식 외에 다른 설명(예: "알겠습니다", "확인 결과")은 생략하고 결과만 출력해줘.
'플랜지 너트: (n)개, 기어 링: (n)개, 스페이서 링: (n)개, 육각 너트: (n)개, 돔 너트: (n)개'""",
    "C": "TODO"
}

class TaskRecognition_VLM_Agent:
    def __init__(
        self,
        zone: str,
        backend: str | None = None,
        model_id: str | None = None,
        vllm_base_url: str | None = None,
    ):
        self.zone = zone
        self.prompt = prompts[zone]
        self.backend = (backend or os.getenv("TR_AGENT_BACKEND", DEFAULT_BACKEND)).lower()
        self.model_id = model_id or os.getenv("VLLM_MODEL", DEFAULT_MODEL_ID)
        self.vllm_base_url = (vllm_base_url or os.getenv("VLLM_BASE_URL", DEFAULT_VLLM_BASE_URL)).rstrip("/")
        self.request_timeout = DEFAULT_REQUEST_TIMEOUT

        print(f"[DEBUG] Initializing TaskRecognition agent with backend: {self.backend}")
        print(f"[DEBUG] Using model: {self.model_id}")
        start_time = time.time()

        if self.backend == "local":
            from vllm import LLM, SamplingParams

            # `vllm serve`에서 사용한 핵심 메모리/컨텍스트 설정을 로컬 Python API에도 맞춘다.
            # host/port/tool parser/reasoning parser 같은 값은 서버 API용 옵션이라 LLM(...)에는 직접 넣지 않는다.
            self.llm = LLM(
                model=self.model_id,
                trust_remote_code=True,
                max_model_len=DEFAULT_MAX_MODEL_LEN,
                gpu_memory_utilization=DEFAULT_GPU_MEMORY_UTILIZATION,
                kv_cache_dtype="fp8",
                load_format="safetensors",
                enable_prefix_caching=True,
                enable_chunked_prefill=True,
                enforce_eager=True,
                disable_log_stats=False,
            )
            self.sampling_params = SamplingParams(
                temperature=0.0,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        elif self.backend == "server":
            self.llm = None
            self.sampling_params = None
        else:
            raise ValueError(f"Unknown TR_AGENT_BACKEND: {self.backend}")

        end_time = time.time()
        print(f"[DEBUG] Agent initialized in {end_time - start_time:.2f} seconds.")

    def _image_to_data_url(self, img_path: str) -> str:
        image_path = Path(img_path)
        mime_type, _ = mimetypes.guess_type(image_path.name)
        if mime_type is None:
            mime_type = "image/jpeg"

        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _build_messages(self, img_path: str | None, prompt_text: str) -> list[dict]:
        content: list[dict] = [{"type": "text", "text": prompt_text}]
        if img_path:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_to_data_url(img_path)},
                }
            )
        return [{"role": "user", "content": content}]

    def _infer_via_server(self, img_path: str | None, prompt_text: str) -> str:
        payload = {
            "model": self.model_id,
            "messages": self._build_messages(img_path, prompt_text),
            "temperature": 0.0,
            "max_tokens": DEFAULT_MAX_TOKENS,
        }

        try:
            response = requests.post(
                f"{self.vllm_base_url}/chat/completions",
                json=payload,
                timeout=self.request_timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                "vLLM 서버에 연결할 수 없습니다. "
                f"현재 주소: {self.vllm_base_url}\n"
                "1. `vllm serve ... --port 30000` 이 실제로 실행 중인지 확인하세요.\n"
                "2. 다른 머신/컨테이너에서 띄웠다면 `--vllm-base-url http://HOST:30000/v1` 로 지정하세요.\n"
                "3. 서버 없이 직접 실행하려면 `TR_AGENT_BACKEND=local` 로 바꾸세요."
            ) from exc
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def main(self, img_path: str | None = None, prompt_text: str | None = None) -> dict:
        final_prompt = prompt_text or self.prompt
        print(f"[DEBUG] Starting Inference for image: {img_path}")

        inf_start = time.time()
        if self.backend == "local":
            messages = self._build_messages(None, final_prompt)
            if img_path:
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": final_prompt},
                            {"type": "image_url", "image_url": {"url": f"file://{img_path}"}},
                        ],
                    }
                ]
            outputs = self.llm.chat(messages, sampling_params=self.sampling_params)
            raw_text = outputs[0].outputs[0].text
        else:
            raw_text = self._infer_via_server(img_path, final_prompt)
        inf_end = time.time()

        print(f"[DEBUG] Raw Gemma Output: '{raw_text}'")
        print(f"[DEBUG] Inference Time: {inf_end - inf_start:.2f}s")

        # Parsing
        matches = re.findall(r'([가-힣 ]+):\s*([0-9]+)개', raw_text)
        object_dict = {item[0].strip(): int(item[1]) for item in matches}
        
        if not object_dict:
            print("[WARNING] Regex failed to parse response. Check 'Raw Gemma Output' above.")
            
        return object_dict
