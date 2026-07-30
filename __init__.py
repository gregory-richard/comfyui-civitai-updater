"""
ComfyUI entrypoint for the Civitai Updater plugin.
"""

try:
    from .comfy_updater.node_info import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, comfy_entrypoint
    from .comfy_updater.plugin import initialize_plugin
except ImportError:  # pragma: no cover - pytest may import this file as a bare module
    from comfy_updater.node_info import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, comfy_entrypoint
    from comfy_updater.plugin import initialize_plugin

WEB_DIRECTORY = "./js"

initialize_plugin()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY", "comfy_entrypoint"]
