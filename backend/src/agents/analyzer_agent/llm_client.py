"""Hugging Face text-generation adapter used by the analyzer."""

from __future__ import annotations

import os
from typing import Any

from huggingface_hub import InferenceClient


class HuggingFaceLLM:
    """Small adapter matching AnalyzerAgent's generate contract."""

    provider = "huggingface"

    def __init__(self, model: str | None = None, token: str | None = None, timeout: float = 120.0):
        self.model = model or os.getenv("HF_RCA_MODEL_ID")
        if not self.model:
            raise ValueError("HF_RCA_MODEL_ID must identify an instruction-tuned text-generation model")
        self.client = InferenceClient(model=self.model, token=token or os.getenv("HUGGINGFACEHUB_API_TOKEN"), timeout=timeout)

    
    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1400,
    ) -> str:
        response = self.client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an incident RCA analyst. "
                        "Return only valid JSON when requested."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content
