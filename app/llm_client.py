# import os
from typing import Optional
from config.config import settings
import httpx
from openai import OpenAI
import re
import json

class LLMClient:
    def __init__(self):
        self.provider = settings.MODEL_PROVIDER
        self.model = settings.MODEL
        self.max_tokens = settings.MAX_TOKENS
        self.temperature = settings.TEMPERATURE
        self.top_p = settings.TOP_P
        self.system_prompt = settings.SYSTEM_PROMPT
        self.client = OpenAI(
                http_client=httpx.Client(),
                api_key = settings.OPENAI_API_KEY
            )

        if self.provider == "openai":
            self.client.api_key = settings.OPENAI_API_KEY
        elif self.provider == "github-models":
            self.client.api_key = settings.GITHUB_TOKEN
            self.client.base_url ="https://models.github.ai/inference"
        elif self.provider == "local":
            from transformers import pipeline
            model_id = settings.MODEL_ID
            self.pipe = pipeline("text-generation", model=model_id)
            self.client = None
        else:
            raise ValueError(f"[LLMClient] Unsupported provider: {self.provider}")

    def chat(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt}
        ]

        if self.provider in {"openai", "github-models"}:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                )
                raw = response.choices[0].message.content.strip()
                print("==== GPT RESPONSE ====")
                print(raw)

                match = re.search(r"```json\n(.*?)```", raw, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
                else:
                    return json.loads(raw)
            except json.JSONDecodeError as e:
                print("JSON parse error:", e)
                return {"summary": "Parse failed", "pass": False, "comments": []}
            except Exception as e:
                print("GPT call failed:", e)
                return {"summary": "Call failed", "pass": False, "comments": []}

        elif self.provider == "local":
            try:
                result = self.pipe(prompt, max_new_tokens=self.max_tokens)[0]["generated_text"]
                return result
            except Exception as e:
                raise RuntimeError(f"[Local Model] Error: {e}")

        else:
            raise ValueError("[LLMClient] No supported chat backend")

