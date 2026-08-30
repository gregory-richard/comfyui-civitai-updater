from __future__ import annotations

# The API must live on civitai.red: since the April 2026 domain split,
# civitai.com ("green" domain) serves SFW-filtered API responses, so hash
# lookups for mature models 404 there. civitai.red serves the full catalog.
API_BASE_URL = "https://civitai.red/api/v1"
MODEL_PAGE_BASE_URL = "https://civitai.red/models"

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
PREVIEW_SIDECAR_SUFFIX = ".preview.png"

CACHE_SCHEMA_VERSION = 2
ARCHIVED_UPDATES_FILENAME = "archived_updates.json"

