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


async def comfy_entrypoint():
    from comfy_api.latest import ComfyExtension, io

    class CivitaiUpdaterStatusNodeV3(io.ComfyNode):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="CivitaiUpdaterStatus",
                display_name="Civitai Updater Status",
                category="Civitai Updater",
                description="Reports whether the Civitai Updater plugin loaded.",
                inputs=[],
                outputs=[
                    io.String.Output("status"),
                ],
            )

        @classmethod
        def execute(cls) -> io.NodeOutput:
            return io.NodeOutput("Civitai Updater plugin loaded")

    class CivitaiUpdaterExtension(ComfyExtension):
        async def get_node_list(self) -> list[type[io.ComfyNode]]:
            return [CivitaiUpdaterStatusNodeV3]

    return CivitaiUpdaterExtension()
