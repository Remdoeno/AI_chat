"""Isolated Qwen Image inference; never imports the Wangcai application."""
import base64
import io
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

MODEL = 'Qwen/Qwen-Image-2.1'
lock = threading.Lock()
pipe = None


@asynccontextmanager
async def lifespan(app):
    global pipe
    import torch
    from diffusers import QwenImage21Pipeline
    pipe = QwenImage21Pipeline.from_pretrained(os.environ['QWEN_IMAGE_MODEL_PATH'], torch_dtype=torch.bfloat16, local_files_only=True).to('cuda')
    pipe.vae.enable_tiling()
    yield
    pipe = None


app = FastAPI(lifespan=lifespan)


class Request(BaseModel):
    model: str = MODEL
    prompt: str = Field(min_length=1, max_length=20000)
    width: int = Field(default=2048, ge=256, le=3072)
    height: int = Field(default=2048, ge=256, le=3072)
    num_inference_steps: int = Field(default=40, ge=1, le=50)
    seed: int = Field(default=42, ge=0, le=2147483647)
    refs_b64: list[str] = Field(default_factory=list, max_length=10)


@app.get('/health')
def health():
    return {'ok': pipe is not None, 'model': MODEL, 'busy': lock.locked()}


@app.post('/v1/images/generations')
def generate(request: Request):
    import torch
    if request.model != MODEL:
        raise HTTPException(400, 'Unknown image model')
    if request.width * request.height > 4600000:
        raise HTTPException(400, 'Maximum image area is 4.6 megapixels')
    if not lock.acquire(timeout=1):
        raise HTTPException(429, 'Qwen image service is busy; try again shortly')
    started = time.monotonic()
    try:
        refs = []
        for raw in request.refs_b64:
            if len(raw) > 24000000:
                raise HTTPException(413, 'Reference image is too large')
            try:
                img = Image.open(io.BytesIO(base64.b64decode(raw.split(',')[-1], validate=True)))
                img.load()
                refs.append(img.convert('RGBA' if 'A' in img.getbands() else 'RGB'))
            except Exception as exc:
                raise HTTPException(400, 'Invalid reference image') from exc
        kwargs = dict(prompt=request.prompt, width=request.width // 32 * 32,
                      height=request.height // 32 * 32, num_inference_steps=request.num_inference_steps,
                      generator=torch.Generator('cuda').manual_seed(request.seed))
        if refs:
            kwargs['image'] = refs
        with torch.inference_mode():
            result = pipe(**kwargs).images[0]
        buf = io.BytesIO()
        result.save(buf, format='PNG')
        seconds = round(time.monotonic() - started, 3)
        logging.warning('Qwen image completed: %sx%s steps=%s seconds=%s', result.width, result.height, request.num_inference_steps, seconds)
        return {'data': [{'b64_json': base64.b64encode(buf.getvalue()).decode()}], 'model': MODEL, 'seconds': seconds}
    except torch.cuda.OutOfMemoryError as exc:
        torch.cuda.empty_cache()
        raise HTTPException(503, 'Insufficient GPU memory for this request') from exc
    finally:
        lock.release()
