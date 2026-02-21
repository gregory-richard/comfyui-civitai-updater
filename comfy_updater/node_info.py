from __future__ import annotations


class CivitaiUpdaterStatusNode:
    @classmethod
    def INPUT_TYPES(cls):  # noqa: N802 - ComfyUI naming convention
        return {"required": {}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "status"
    CATEGORY = "Civitai Updater"

    def status(self):
        return ("Civitai Updater plugin loaded",)


NODE_CLASS_MAPPINGS = {
    "CivitaiUpdaterStatus": CivitaiUpdaterStatusNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CivitaiUpdaterStatus": "Civitai Updater Status",
}

