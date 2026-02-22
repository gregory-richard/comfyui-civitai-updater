# Publishing Checklist (Comfy Registry)

1. Fill placeholders in `pyproject.toml`:
   - `tool.comfy.PublisherId`
   - confirm `tool.comfy.Icon` / `tool.comfy.Banner` raw GitHub URLs
2. Push assets:
   - `assets/registry/icon.png` (400x400)
   - `assets/registry/banner.png` (21:9)
3. Create a Comfy Registry API key and add GitHub secret:
   - `REGISTRY_ACCESS_TOKEN`
4. Commit and push to `main` with `pyproject.toml` version bump.
5. Publishing runs via `.github/workflows/publish_action.yml`.

Manual alternative:

```bash
comfy node publish
```
