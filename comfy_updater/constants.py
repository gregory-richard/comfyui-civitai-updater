from __future__ import annotations

API_BASE_URL = "https://civitai.com/api/v1"
MODEL_PAGE_BASE_URL = "https://civitai.com/models"

VERSION_BY_HASH_URL = f"{API_BASE_URL}/model-versions/by-hash"
MODEL_BY_ID_URL = f"{API_BASE_URL}/models"
MODEL_VERSION_BY_ID_URL = f"{API_BASE_URL}/model-versions"

SUPPORTED_MODEL_TYPES = ("checkpoint", "lora", "vae", "unet", "embedding")

MODEL_TYPE_TO_COMFY_KEYS = {
    "checkpoint": ("checkpoints",),
    "lora": ("loras",),
    "vae": ("vae",),
    "unet": ("diffusion_models", "unet"),
    "embedding": ("embeddings",),
}

SUPPORTED_MODEL_EXTENSIONS = (
    ".ckpt",
    ".pt",
    ".pt2",
    ".bin",
    ".pth",
    ".safetensors",
    ".pkl",
    ".sft",
    ".gguf",
)

INFO_SIDECAR_SUFFIX = ".civitai.info"
PREVIEW_SIDECAR_SUFFIX = ".preview.jpeg"

