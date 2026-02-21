from __future__ import annotations

from pathlib import Path

from .constants import MODEL_TYPE_TO_COMFY_KEYS, SUPPORTED_MODEL_EXTENSIONS, SUPPORTED_MODEL_TYPES

try:
    import folder_paths
except ModuleNotFoundError:  # pragma: no cover - only happens outside ComfyUI
    folder_paths = None

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - only happens outside ComfyUI
    yaml = None

try:
    from comfy.cli_args import args as comfy_args
except ModuleNotFoundError:  # pragma: no cover - only happens outside ComfyUI
    comfy_args = None


def resolve_model_roots(config: dict, model_types: list[str], include_custom_paths: bool) -> dict[str, list[Path]]:
    roots: dict[str, list[Path]] = {}
    use_comfy_paths = bool(config.get("useComfyPaths", True))
    use_extra_paths = bool(config.get("useExtraModelPaths", True))
    use_custom_paths = bool(config.get("useCustomPaths", True))

    for model_type in model_types:
        roots[model_type] = []
        if use_comfy_paths:
            for root in _resolve_comfy_paths(model_type):
                if root not in roots[model_type]:
                    roots[model_type].append(root)

        # Comfy normally injects these into folder_paths already, but this
        # explicit pass guarantees we include extra_model_paths.yaml entries.
        if use_extra_paths:
            for root in _resolve_extra_yaml_paths(model_type):
                if root not in roots[model_type]:
                    roots[model_type].append(root)

        if include_custom_paths and use_custom_paths:
            custom = config.get("customPaths", {}).get(model_type, [])
            for path in custom:
                root = Path(path).expanduser().resolve()
                if root not in roots[model_type]:
                    roots[model_type].append(root)

    return roots


def list_model_files(roots: dict[str, list[Path]]) -> list[dict]:
    files: list[dict] = []
    for model_type, model_roots in roots.items():
        for root in model_roots:
            if not root.is_dir():
                continue
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in SUPPORTED_MODEL_EXTENSIONS:
                    continue
                files.append({"modelType": model_type, "path": file_path})
    return files


def normalize_model_types(raw_types: list[str] | None) -> list[str]:
    if not raw_types:
        return list(SUPPORTED_MODEL_TYPES)
    normalized = []
    for entry in raw_types:
        value = (entry or "").strip().lower()
        if value in SUPPORTED_MODEL_TYPES and value not in normalized:
            normalized.append(value)
    return normalized or list(SUPPORTED_MODEL_TYPES)


def _resolve_comfy_paths(model_type: str) -> list[Path]:
    if folder_paths is None:
        return []

    resolved: list[Path] = []
    for comfy_key in MODEL_TYPE_TO_COMFY_KEYS.get(model_type, ()):
        try:
            roots = folder_paths.get_folder_paths(comfy_key)
        except Exception:
            roots = []
        for root in roots:
            path = Path(root).expanduser().resolve()
            if path not in resolved:
                resolved.append(path)
    return resolved


def _resolve_extra_yaml_paths(model_type: str) -> list[Path]:
    if yaml is None:
        return []

    yaml_paths = _discover_extra_yaml_paths()
    if not yaml_paths:
        return []

    acceptable_keys = set(MODEL_TYPE_TO_COMFY_KEYS.get(model_type, ()))
    # keep legacy spelling in case a user writes "unet" in yaml
    if model_type == "unet":
        acceptable_keys.add("unet")

    results: list[Path] = []
    for yaml_path in yaml_paths:
        parsed = _parse_extra_model_yaml(yaml_path)
        for key, paths in parsed.items():
            if key not in acceptable_keys:
                continue
            for path in paths:
                if path not in results:
                    results.append(path)
    return results


def _discover_extra_yaml_paths() -> list[Path]:
    paths: list[Path] = []

    if folder_paths is not None:
        comfy_root = Path(folder_paths.__file__).resolve().parent
        default_yaml = comfy_root / "extra_model_paths.yaml"
        if default_yaml.is_file():
            paths.append(default_yaml)

    if comfy_args is not None and getattr(comfy_args, "extra_model_paths_config", None):
        for group in comfy_args.extra_model_paths_config:
            for candidate in group:
                candidate_path = Path(candidate).expanduser().resolve()
                if candidate_path.is_file() and candidate_path not in paths:
                    paths.append(candidate_path)

    return paths


def _parse_extra_model_yaml(yaml_path: Path) -> dict[str, list[Path]]:
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}

    if not isinstance(raw, dict):
        return {}

    by_key: dict[str, list[Path]] = {}
    yaml_dir = yaml_path.parent

    for _, conf in raw.items():
        if not isinstance(conf, dict):
            continue

        base_path = conf.get("base_path")
        if isinstance(base_path, str) and base_path.strip():
            base = Path(base_path).expanduser()
            if not base.is_absolute():
                base = (yaml_dir / base).resolve()
        else:
            base = None

        for key, raw_paths in conf.items():
            if key in ("base_path", "is_default"):
                continue
            if not isinstance(raw_paths, str):
                continue

            key_paths = by_key.setdefault(key, [])
            for line in raw_paths.splitlines():
                line = line.strip()
                if not line:
                    continue

                candidate = Path(line).expanduser()
                if base is not None:
                    candidate = (base / candidate).resolve()
                elif not candidate.is_absolute():
                    candidate = (yaml_dir / candidate).resolve()
                else:
                    candidate = candidate.resolve()

                if candidate not in key_paths:
                    key_paths.append(candidate)

    return by_key
