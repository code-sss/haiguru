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


def save_raw_response(output_dir, filename, content):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
