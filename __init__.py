"""
ComfyUI entrypoint for the Civitai Updater plugin.
"""

from .comfy_updater.node_info import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .comfy_updater.plugin import initialize_plugin

WEB_DIRECTORY = "./js"

initialize_plugin()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
