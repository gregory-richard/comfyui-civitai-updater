# Publishing Checklist (Comfy Registry)

1. Check `pyproject.toml`:
   - `tool.comfy.PublisherId` is the publisher slug from your Registry profile
     (currently `gregrichrd`), not the API token and not a UUID.
   - `tool.comfy.Icon` / `tool.comfy.Banner` point at the raw GitHub URLs of
     `assets/registry/icon.png` (400x400) and `assets/registry/banner.png` (21:9).
2. Move the `## [Unreleased]` notes in `CHANGELOG.md` under the new version
   and date, and bump `version` in `pyproject.toml`.
3. Make sure the `REGISTRY_ACCESS_TOKEN` GitHub secret holds a valid Comfy
   Registry API key.
4. Commit and push to `main`. Any push that touches `pyproject.toml` runs
   `.github/workflows/publish_action.yml` and publishes to the Registry, so
   keep version bumps in their own commit.

Manual alternative:

```bash
comfy node publish
```
