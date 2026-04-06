import requests
import base64
import time
import os
from io import BytesIO
from PIL import Image
import ollama


def get_optimized_image_b64(source):
    """Load (URL or local) and return a JPEG-encoded Base64 string."""
    if source.startswith("http://") or source.startswith("https://"):
        response = requests.get(source)
        img = Image.open(BytesIO(response.content))
    else:
        img = Image.open(source)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=95)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def send_streamed_request(model, prompt, images_b64):
    """Invoke `ollama.generate` in streaming mode and yield events.

    Yields tuples (tag, payload):
      - ("__first_token__", seconds_to_first_token)
      - ("chunk", text_chunk)
      - ("__done__", total_seconds)
    """
    start_time = time.time()
    stream = ollama.generate(model=model, prompt=prompt, images=images_b64, stream=True,
                             options={"num_ctx": 8192, "num_predict": 4096})
    first = True
    for chunk in stream:
        if first:
            yield ("__first_token__", time.time() - start_time)
            first = False
        yield ("chunk", chunk.get("response", ""))
    yield ("__done__", time.time() - start_time)


def send_single_request(model, prompt, images_b64):
    """Invoke `ollama.generate` without streaming and return the full response text."""
    result = ollama.generate(model=model, prompt=prompt, images=images_b64, stream=False,
                             options={"num_ctx": 8192, "num_predict": 4096})
    return result.get("response", "")


def send_text_request(model, prompt):
    """Invoke `ollama.generate` with a text-only prompt and return the full response."""
    result = ollama.generate(model=model, prompt=prompt, stream=False,
                             options={"num_ctx": 8192, "num_predict": 4096})
    return result.get("response", "")


def _strip_no_think(prompt: str) -> str:
    """Remove the /no_think directive used only by Ollama/qwen3 models."""
    if prompt.startswith("/no_think\n"):
        return prompt[len("/no_think\n"):]
    return prompt


def _openai_text_stream(model_name: str, prompt: str, base_url: str | None, api_key_env: str):
    """Yield text chunks from an OpenAI-compatible chat completions API (streaming)."""
    import openai as _openai
    api_key = os.environ.get(api_key_env)
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = _openai.OpenAI(**kwargs)
    stream = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        max_tokens=4096,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def _anthropic_text_stream(model_name: str, prompt: str):
    """Yield the full response as a single chunk from the Anthropic Messages API."""
    import anthropic as _anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = _anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model_name,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    yield message.content[0].text


def send_text_request_streaming(model, prompt):
    """Streaming text request — routes to Ollama, OpenAI, Anthropic, or TogetherAI.

    Model name conventions:
      openai://gpt-4o              — OpenAI (OPENAI_API_KEY)
      anthropic://claude-3-5-...  — Anthropic (ANTHROPIC_API_KEY)
      together://<model-path>     — TogetherAI OpenAI-compat (TOGETHER_API_KEY)
      <plain-name>                — Ollama (local)
    """
    if "://" in model:
        provider, model_name = model.split("://", 1)
        clean_prompt = _strip_no_think(prompt)
        if provider == "openai":
            yield from _openai_text_stream(model_name, clean_prompt, base_url=None, api_key_env="OPENAI_API_KEY")
        elif provider == "anthropic":
            yield from _anthropic_text_stream(model_name, clean_prompt)
        elif provider == "together":
            yield from _openai_text_stream(
                model_name, clean_prompt,
                base_url="https://api.together.xyz/v1",
                api_key_env="TOGETHER_API_KEY",
            )
        else:
            raise ValueError(f"[glm_ocr] Unknown LLM provider: {provider!r}. Use openai://, anthropic://, together://, or a plain Ollama model name.")
    else:
        # Ollama (original behaviour)
        stream = ollama.generate(model=model, prompt=prompt, stream=True,
                                 options={"num_ctx": 8192, "num_predict": 4096})
        for chunk in stream:
            yield chunk.get("response", "")


def save_raw_response(output_dir, filename, content):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
