import base64
import os
from dataclasses import dataclass
from typing import List, Optional

import requests

from src.utils.api_keys import get_primary_provider_key


@dataclass
class GeneratedImage:
    image_bytes: bytes
    mime_type: str
    provider: str
    model: str
    prompt_used: str


class ThumbnailGenerator:
    def __init__(self, provider: str, api_key: str, model: str):
        self.provider = provider.lower().strip()
        self.api_key = api_key.strip()
        self.model = model.strip()
        if not self.api_key:
            raise ValueError("Missing API key.")

    def generate(
        self,
        title: str,
        context: str,
        style: str,
        negative_prompt: str,
        count: int = 1,
        size: str = "1536x1024",
        quality: Optional[str] = None,
    ) -> List[GeneratedImage]:
        prompt = self._build_prompt(title, context, style, negative_prompt)
        if self.provider == "gemini":
            return self._generate_with_gemini(prompt=prompt, count=count)
        if self.provider == "openai":
            return self._generate_with_openai(
                prompt=prompt,
                count=count,
                size=size,
                quality=quality,
            )
        raise ValueError(f"Unsupported provider: {self.provider}")

    @staticmethod
    def _build_prompt(title: str, context: str, style: str, negative_prompt: str) -> str:
        clean_title = title.strip()
        clean_context = context.strip()
        clean_style = style.strip()
        clean_negative = negative_prompt.strip()
        return (
            "Create a high CTR YouTube thumbnail concept image.\n"
            f"Video title: {clean_title}\n"
            f"Context: {clean_context}\n"
            f"Visual style: {clean_style}\n"
            "Target format: 16:9 composition suitable for YouTube.\n"
            "Focus on one clear subject, bold contrast, and legible central composition.\n"
            "Do not place small unreadable text.\n"
            f"Avoid these elements: {clean_negative if clean_negative else 'None'}\n"
        )

    def _generate_with_gemini(self, prompt: str, count: int) -> List[GeneratedImage]:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        images: List[GeneratedImage] = []
        for _ in range(count):
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            }
            response = requests.post(endpoint, json=payload, timeout=90)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Gemini API error ({response.status_code}): {response.text[:500]}"
                )
            body = response.json()
            parsed = self._extract_gemini_images(body, prompt)
            if not parsed:
                raise RuntimeError(
                    "Gemini returned no image data. Try another Gemini image model."
                )
            images.extend(parsed)
        return images

    def _extract_gemini_images(self, body: dict, prompt: str) -> List[GeneratedImage]:
        out: List[GeneratedImage] = []
        for candidate in body.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if not inline:
                    continue
                b64 = inline.get("data")
                if not b64:
                    continue
                mime_type = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                out.append(
                    GeneratedImage(
                        image_bytes=base64.b64decode(b64),
                        mime_type=mime_type,
                        provider="gemini",
                        model=self.model,
                        prompt_used=prompt,
                    )
                )
        return out

    def _generate_with_openai(
        self,
        prompt: str,
        count: int,
        size: str,
        quality: Optional[str],
    ) -> List[GeneratedImage]:
        endpoint = "https://api.openai.com/v1/images/generations"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "prompt": prompt, "n": count, "size": size}
        if quality:
            payload["quality"] = quality
        response = requests.post(endpoint, headers=headers, json=payload, timeout=90)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenAI API error ({response.status_code}): {response.text[:500]}"
            )
        body = response.json()
        out: List[GeneratedImage] = []
        for item in body.get("data", []):
            b64 = item.get("b64_json")
            if not b64:
                continue
            out.append(
                GeneratedImage(
                    image_bytes=base64.b64decode(b64),
                    mime_type="image/png",
                    provider="openai",
                    model=self.model,
                    prompt_used=prompt,
                )
            )
        if not out:
            raise RuntimeError("OpenAI returned no image data.")
        return out


def get_api_key(provider: str) -> Optional[str]:
    provider_name = provider.lower().strip()
    pooled_key = get_primary_provider_key(provider_name)
    if pooled_key:
        return pooled_key
    if provider_name == "gemini":
        return os.getenv("GEMINI_API_KEY")
    if provider_name == "openai":
        return os.getenv("OPENAI_API_KEY")
    return None
