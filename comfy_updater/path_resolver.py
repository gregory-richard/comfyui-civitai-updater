from __future__ import annotations

from pathlib import Path

from .constants import (
    INFO_SIDECAR_SUFFIX,
    MODEL_TYPE_TO_COMFY_KEYS,
    PREVIEW_SIDECAR_SUFFIX,
    SUPPORTED_MODEL_EXTENSIONS,
    SUPPORTED_MODEL_TYPES,
)
from .sidecar import (
    SIDECAR_ERROR_INVALID_ENCODING,
    SIDECAR_ERROR_INVALID_JSON,
    SIDECAR_ERROR_READ,
    SIDECAR_ERROR_SAFETENSORS,
    SIDECAR_ERROR_TOO_LARGE,
    read_json_diagnostic,
)

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


def list_model_files(
    roots: dict[str, list[Path]],
    include_sidecar_only: bool = False,
    sidecar_warnings: list[dict] | None = None,
) -> list[dict]:
    files: list[dict] = []
    weight_stems: set[str] = set()
    sidecar_candidates: list[tuple[str, Path]] = []

    for model_type, model_roots in roots.items():
        for root in model_roots:
            if not root.is_dir():
                continue
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() in SUPPORTED_MODEL_EXTENSIONS:
                    weight_stems.add(_weight_stem_key(file_path))
                    files.append(
                        {
                            "modelType": model_type,
                            "path": file_path,
                            "infoPath": file_path.with_suffix(INFO_SIDECAR_SUFFIX),
                            "previewPath": file_path.with_suffix(PREVIEW_SIDECAR_SUFFIX),
                            "metadataOnly": False,
                        }
                    )
                elif include_sidecar_only and file_path.name.lower().endswith(INFO_SIDECAR_SUFFIX):
                    sidecar_candidates.append((model_type, file_path))

    if include_sidecar_only:
        for model_type, info_path in sidecar_candidates:
            if _info_stem_key(info_path) in weight_stems:
                continue
            if not _is_valid_info_sidecar(info_path, sidecar_warnings):
                continue
            files.append(
                {
                    "modelType": model_type,
                    "path": info_path,
                    "infoPath": info_path,
                    "previewPath": _preview_path_for_info(info_path),
                    "metadataOnly": True,
                }
            )

    return files


def _weight_stem_key(model_path: Path) -> str:
    return str(model_path.with_suffix("")).lower()


def _info_stem_key(info_path: Path) -> str:
    return str(info_path.with_name(info_path.name[: -len(INFO_SIDECAR_SUFFIX)])).lower()


def _preview_path_for_info(info_path: Path) -> Path:
    base_name = info_path.name[: -len(INFO_SIDECAR_SUFFIX)]
    return info_path.with_name(f"{base_name}{PREVIEW_SIDECAR_SUFFIX}")


def _is_valid_info_sidecar(info_path: Path, sidecar_warnings: list[dict] | None = None) -> bool:
    payload, error = read_json_diagnostic(info_path)
    if error and sidecar_warnings is not None:
        _append_sidecar_warning(sidecar_warnings, info_path, error)
    if not isinstance(payload, dict):
        return False
    return _has_identifier(payload.get("modelId")) and _has_identifier(payload.get("id"))


def _append_sidecar_warning(warnings: list[dict], info_path: Path, error: str) -> None:
    path = str(info_path)
    if any(str(warning.get("path", "")).lower() == path.lower() for warning in warnings):
        return

    messages = {
        SIDECAR_ERROR_SAFETENSORS: (
            "This appears to be a SafeTensors model saved with the .civitai.info extension. "
            "Rename it to use the .safetensors extension."
        ),
        SIDECAR_ERROR_TOO_LARGE: "This metadata sidecar is implausibly large and was ignored.",
        SIDECAR_ERROR_INVALID_ENCODING: "This sidecar is not valid UTF-8, UTF-16, or UTF-32 JSON and was ignored.",
        SIDECAR_ERROR_INVALID_JSON: "This sidecar contains malformed JSON and was ignored.",
        SIDECAR_ERROR_READ: "This sidecar could not be read and was ignored.",
    }
    warnings.append(
        {
            "path": path,
            "code": error,
            "message": messages.get(error, "This sidecar is invalid and was ignored."),
            "suggestedExtension": ".safetensors" if error == SIDECAR_ERROR_SAFETENSORS else "",
        }
    )


def _has_identifier(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, str)) and bool(str(value).strip())


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
