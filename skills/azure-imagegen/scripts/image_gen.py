#!/usr/bin/env python3
"""Generate or edit images with Azure OpenAI v1 Image API."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from io import BytesIO

DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_CONCURRENCY = 5
DEFAULT_DOWNSCALE_SUFFIX = "-web"
DEFAULT_TRANSPARENT_FUZZ = 6.0

DEFAULT_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
DEFAULT_DEPLOYMENT_ENV = "AZURE_OPENAI_DEPLOYMENT"
DEFAULT_API_KEY_ENV = "AZURE_OPENAI_API_KEY"
DEFAULT_ENTRA_SCOPE = "https://ai.azure.com/.default"

ALLOWED_SIZES = {"1024x1024", "1536x1024", "1024x1536"}
ALLOWED_QUALITIES = {"low", "medium", "high"}
ALLOWED_BACKGROUNDS = {"transparent", "opaque", "auto", None}
ALLOWED_AUTH_MODES = {"api-key", "entra"}

MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_BATCH_JOBS = 500
GPT_IMAGE_2_MIN_PIXELS = 655_360
GPT_IMAGE_2_MAX_PIXELS = 8_294_400


@dataclass(frozen=True)
class ResolvedValue:
    value: Optional[str]
    source: str
    env_name: Optional[str] = None


@dataclass(frozen=True)
class AzureRuntimeConfig:
    base_url: str
    endpoint_source: str
    deployment: str
    deployment_source: str
    auth_mode: str
    api_key: Optional[str]
    api_key_source: Optional[str]
    api_key_env_name: Optional[str]
    entra_scope: str


def _die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def _read_prompt(prompt: Optional[str], prompt_file: Optional[str]) -> str:
    if prompt and prompt_file:
        _die("Use --prompt or --prompt-file, not both.")
    if prompt_file:
        path = Path(prompt_file)
        if not path.exists():
            _die(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    if prompt:
        return prompt.strip()
    _die("Missing prompt. Use --prompt or --prompt-file.")
    return ""  # unreachable


def _check_image_paths(paths: Iterable[str]) -> List[Path]:
    resolved: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            _die(f"Image file not found: {path}")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            _warn(f"Image exceeds 50MB limit: {path}")
        resolved.append(path)
    return resolved


def _normalize_output_format(fmt: Optional[str]) -> str:
    if not fmt:
        return DEFAULT_OUTPUT_FORMAT
    fmt = fmt.lower()
    if fmt not in {"png", "jpeg", "jpg", "webp"}:
        _die("output-format must be png, jpeg, jpg, or webp.")
    return "jpeg" if fmt == "jpg" else fmt


def _is_gpt_image_2_deployment(deployment: str) -> bool:
    return "gpt-image-2" in deployment.lower()


def _parse_size(size: str) -> Optional[Tuple[int, int]]:
    match = re.fullmatch(r"(\d+)x(\d+)", size.lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _validate_size(size: Optional[str], *, deployment: str) -> None:
    if not _is_gpt_image_2_deployment(deployment):
        if size is not None and size not in ALLOWED_SIZES:
            _die(
                "size must be one of 1024x1024, 1536x1024, or 1024x1536 for Azure image deployments."
            )
        return

    if size is None:
        return

    parsed = _parse_size(size)
    if parsed is None:
        _die("size must be WIDTHxHEIGHT or omitted for GPT-image-2 deployments.")

    width, height = parsed
    if width % 16 != 0 or height % 16 != 0:
        _die("GPT-image-2 size dimensions must each be a multiple of 16.")

    pixels = width * height
    if pixels < GPT_IMAGE_2_MIN_PIXELS:
        _die("GPT-image-2 size must be at least 655,360 total pixels.")
    if pixels > GPT_IMAGE_2_MAX_PIXELS:
        _warn(
            "GPT-image-2 requested size exceeds 8,294,400 pixels; Azure may resize the final image to fit."
        )


def _effective_size(size: Optional[str], *, deployment: str) -> Optional[str]:
    if size is not None:
        return size
    if _is_gpt_image_2_deployment(deployment):
        return None
    return DEFAULT_SIZE


def _validate_quality(quality: str) -> None:
    if quality not in ALLOWED_QUALITIES:
        _die("quality must be one of low, medium, or high.")


def _validate_background(background: Optional[str]) -> None:
    if background not in ALLOWED_BACKGROUNDS:
        _die("background must be one of transparent, opaque, or auto.")


def _validate_transparency(
    background: Optional[str],
    output_format: str,
    *,
    deployment: str,
) -> None:
    if background == "transparent" and _is_gpt_image_2_deployment(deployment):
        _die(
            "GPT-image-2 does not support background=transparent. Use a GPT-image-1/1.5 "
            "deployment for native transparent output, or generate on a flat key color "
            "and run postprocess-transparent."
        )
    if background == "transparent" and output_format not in {"png", "webp"}:
        _die("transparent background requires output-format png or webp.")


def _validate_generate_payload(payload: Dict[str, Any]) -> None:
    n = int(payload.get("n", 1))
    if n < 1 or n > 10:
        _die("n must be between 1 and 10")
    deployment = str(payload.get("model", ""))
    size = payload.get("size")
    quality = str(payload.get("quality", DEFAULT_QUALITY))
    background = payload.get("background")
    _validate_size(str(size) if size is not None else None, deployment=deployment)
    _validate_quality(quality)
    _validate_background(background)
    oc = payload.get("output_compression")
    if oc is not None and not (0 <= int(oc) <= 100):
        _die("output_compression must be between 0 and 100")


def _build_output_paths(
    out: str,
    output_format: str,
    count: int,
    out_dir: Optional[str],
    *,
    create_dirs: bool = True,
) -> List[Path]:
    ext = "." + output_format

    if out_dir:
        out_base = Path(out_dir)
        if create_dirs:
            out_base.mkdir(parents=True, exist_ok=True)
        return [out_base / f"image_{i}{ext}" for i in range(1, count + 1)]

    out_path = Path(out)
    if out_path.exists() and out_path.is_dir():
        out_path.mkdir(parents=True, exist_ok=True)
        return [out_path / f"image_{i}{ext}" for i in range(1, count + 1)]

    if out_path.suffix == "":
        out_path = out_path.with_suffix(ext)
    elif output_format and out_path.suffix.lstrip(".").lower() != output_format:
        _warn(
            f"Output extension {out_path.suffix} does not match output-format {output_format}."
        )

    if count == 1:
        return [out_path]

    return [
        out_path.with_name(f"{out_path.stem}-{i}{out_path.suffix}")
        for i in range(1, count + 1)
    ]


def _augment_prompt(args: argparse.Namespace, prompt: str) -> str:
    fields = _fields_from_args(args)
    return _augment_prompt_fields(args.augment, prompt, fields)


def _augment_prompt_fields(augment: bool, prompt: str, fields: Dict[str, Optional[str]]) -> str:
    if not augment:
        return prompt

    sections: List[str] = []
    if fields.get("use_case"):
        sections.append(f"Use case: {fields['use_case']}")
    if fields.get("asset_type"):
        sections.append(f"Asset type: {fields['asset_type']}")
    sections.append(f"Primary request: {prompt}")
    if fields.get("scene"):
        sections.append(f"Scene/background: {fields['scene']}")
    if fields.get("subject"):
        sections.append(f"Subject: {fields['subject']}")
    if fields.get("style"):
        sections.append(f"Style/medium: {fields['style']}")
    if fields.get("composition"):
        sections.append(f"Composition/framing: {fields['composition']}")
    if fields.get("lighting"):
        sections.append(f"Lighting/mood: {fields['lighting']}")
    if fields.get("palette"):
        sections.append(f"Color palette: {fields['palette']}")
    if fields.get("materials"):
        sections.append(f"Materials/textures: {fields['materials']}")
    if fields.get("text"):
        sections.append(f"Text (verbatim): \"{fields['text']}\"")
    if fields.get("constraints"):
        sections.append(f"Constraints: {fields['constraints']}")
    if fields.get("negative"):
        sections.append(f"Avoid: {fields['negative']}")

    return "\n".join(sections)


def _fields_from_args(args: argparse.Namespace) -> Dict[str, Optional[str]]:
    return {
        "use_case": getattr(args, "use_case", None),
        "asset_type": getattr(args, "asset_type", None),
        "scene": getattr(args, "scene", None),
        "subject": getattr(args, "subject", None),
        "style": getattr(args, "style", None),
        "composition": getattr(args, "composition", None),
        "lighting": getattr(args, "lighting", None),
        "palette": getattr(args, "palette", None),
        "materials": getattr(args, "materials", None),
        "text": getattr(args, "text", None),
        "constraints": getattr(args, "constraints", None),
        "negative": getattr(args, "negative", None),
    }


def _print_request(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))

def _derive_downscale_path(path: Path, suffix: str) -> Path:
    if suffix and not suffix.startswith("-") and not suffix.startswith("_"):
        suffix = "-" + suffix
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def _preflight_outputs(
    outputs: List[Path],
    *,
    force: bool,
    downscale_max_dim: Optional[int],
    downscale_suffix: str,
) -> None:
    planned = list(outputs)
    if downscale_max_dim is not None:
        planned.extend(_derive_downscale_path(path, downscale_suffix) for path in outputs)
    seen = set()
    for path in planned:
        resolved = path.resolve()
        if resolved in seen:
            _die(f"Output paths overlap: {path}. Choose unique output names and downscale suffixes.")
        seen.add(resolved)
        if path.is_dir():
            _die(f"Output path is a directory: {path}")
        if path.exists() and not force:
            _die(f"Output already exists: {path} (use --force to overwrite)")
        for parent in path.parents:
            if parent.exists() and not parent.is_dir():
                _die(f"Output parent is not a directory: {parent}")
    for parent in {path.parent for path in planned}:
        parent.mkdir(parents=True, exist_ok=True)


def _downscale_image_bytes(image_bytes: bytes, *, max_dim: int, output_format: str) -> bytes:
    try:
        from PIL import Image
    except Exception:
        _die(
            "Downscaling requires Pillow. Install with `python -m pip install pillow` "
            "or `uv pip install pillow` (then re-run)."
        )

    if max_dim < 1:
        _die("--downscale-max-dim must be >= 1")

    with Image.open(BytesIO(image_bytes)) as img:
        img.load()
        w, h = img.size
        scale = min(1.0, float(max_dim) / float(max(w, h)))
        target = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))

        resized = img if target == (w, h) else img.resize(target, Image.Resampling.LANCZOS)

        fmt = output_format.lower()
        if fmt == "jpg":
            fmt = "jpeg"

        if fmt == "jpeg":
            if resized.mode in ("RGBA", "LA") or ("transparency" in getattr(resized, "info", {})):
                bg = Image.new("RGB", resized.size, (255, 255, 255))
                bg.paste(resized.convert("RGBA"), mask=resized.convert("RGBA").split()[-1])
                resized = bg
            else:
                resized = resized.convert("RGB")

        out = BytesIO()
        resized.save(out, format=fmt.upper())
        return out.getvalue()


def _decode_write_and_downscale(
    images: List[str],
    outputs: List[Path],
    *,
    force: bool,
    downscale_max_dim: Optional[int],
    downscale_suffix: str,
    output_format: str,
) -> None:
    for idx, image_b64 in enumerate(images):
        if idx >= len(outputs):
            break
        out_path = outputs[idx]
        if out_path.exists() and not force:
            _die(f"Output already exists: {out_path} (use --force to overwrite)")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        raw = base64.b64decode(image_b64)
        out_path.write_bytes(raw)
        print(f"Wrote {out_path}")

        if downscale_max_dim is None:
            continue

        derived = _derive_downscale_path(out_path, downscale_suffix)
        if derived.exists() and not force:
            _die(f"Output already exists: {derived} (use --force to overwrite)")
        derived.parent.mkdir(parents=True, exist_ok=True)
        resized = _downscale_image_bytes(raw, max_dim=downscale_max_dim, output_format=output_format)
        derived.write_bytes(resized)
        print(f"Wrote {derived}")


def _format_fuzz(fuzz: float) -> str:
    return f"{fuzz:g}%"


def _magick_transparent_command(
    *,
    magick_bin: str,
    input_path: Path,
    output_path: Path,
    key_color: str,
    fuzz: float,
    trim: bool,
) -> List[str]:
    command = [
        magick_bin,
        str(input_path),
        "-alpha",
        "set",
        "-fuzz",
        _format_fuzz(fuzz),
        "-transparent",
        key_color,
    ]
    if trim:
        command.extend(["-trim", "+repage"])
    command.append(str(output_path))
    return command


def _postprocess_transparent(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.out)
    key_color = args.key_color.strip()
    fuzz = float(args.fuzz)

    if not input_path.exists():
        _die(f"Input image not found: {input_path}")
    if output_path.suffix.lower() != ".png":
        _die("postprocess-transparent output must be a PNG file.")
    if output_path.exists() and not args.force and not args.dry_run:
        _die(f"Output already exists: {output_path} (use --force to overwrite)")
    if not key_color:
        _die("--key-color cannot be empty")
    if fuzz < 0 or fuzz > 100:
        _die("--fuzz must be between 0 and 100")

    magick_bin = shutil.which("magick")
    if magick_bin is None:
        if args.dry_run:
            magick_bin = "magick"
        else:
            _die("ImageMagick `magick` was not found on PATH. Install ImageMagick or add it to PATH.")

    command = _magick_transparent_command(
        magick_bin=magick_bin,
        input_path=input_path,
        output_path=output_path,
        key_color=key_color,
        fuzz=fuzz,
        trim=args.trim,
    )

    preview = {"command": command, "output": str(output_path)}
    if args.dry_run:
        _print_request(preview)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        _die(f"ImageMagick failed with exit code {exc.returncode}.")
    print(f"Wrote {output_path}")


def _normalize_base_url(endpoint: str) -> str:
    endpoint = endpoint.strip()
    if not endpoint:
        _die("endpoint cannot be empty.")
    if not endpoint.startswith("https://"):
        _die("endpoint must start with https://")

    trimmed = endpoint.rstrip("/")
    if "/openai/v1/" in trimmed and not trimmed.endswith("/openai/v1"):
        _die("endpoint must be the resource root or the /openai/v1 base URL.")
    if trimmed.endswith("/openai/v1"):
        return trimmed + "/"
    if "/openai/" in trimmed:
        _die("endpoint must be the resource root or the /openai/v1 base URL.")
    return trimmed + "/openai/v1/"


def _resolve_value(
    *,
    flag_value: Optional[str],
    env_name_flag: Optional[str],
    default_env_name: str,
    label: str,
    flag_name: str,
    allow_missing_in_dry_run: bool,
    dry_run: bool,
) -> ResolvedValue:
    if flag_value:
        value = flag_value.strip()
        if value:
            return ResolvedValue(value=value, source=f"flag:{flag_name}")
        _die(f"{label} cannot be empty.")

    env_name = env_name_flag.strip() if env_name_flag else default_env_name
    if not env_name:
        _die(f"No environment variable name available for {label}.")
    env_value = os.getenv(env_name)
    if env_value is not None and env_value.strip():
        return ResolvedValue(value=env_value.strip(), source=f"env:{env_name}", env_name=env_name)

    if flag_name.endswith("-env"):
        message = f"{label} is not set. Set {env_name}."
        if not env_name_flag:
            message += f" Or use --{flag_name} to choose a different env var name."
    else:
        message = f"{label} is not set. Provide --{flag_name} or set {env_name}."
    if dry_run and allow_missing_in_dry_run:
        _warn(message + " Dry-run only.")
        return ResolvedValue(value=None, source=f"missing:{env_name}", env_name=env_name)
    _die(message)
    return ResolvedValue(value=None, source="missing", env_name=env_name)


def _resolve_runtime_config(args: argparse.Namespace) -> AzureRuntimeConfig:
    endpoint = _resolve_value(
        flag_value=args.endpoint,
        env_name_flag=args.endpoint_env,
        default_env_name=DEFAULT_ENDPOINT_ENV,
        label="endpoint",
        flag_name="endpoint",
        allow_missing_in_dry_run=False,
        dry_run=args.dry_run,
    )
    deployment = _resolve_value(
        flag_value=args.deployment,
        env_name_flag=args.deployment_env,
        default_env_name=DEFAULT_DEPLOYMENT_ENV,
        label="deployment",
        flag_name="deployment",
        allow_missing_in_dry_run=False,
        dry_run=args.dry_run,
    )

    api_key: Optional[ResolvedValue] = None
    if args.auth_mode == "api-key":
        api_key = _resolve_value(
            flag_value=None,
            env_name_flag=args.api_key_env,
            default_env_name=DEFAULT_API_KEY_ENV,
            label="api key",
            flag_name="api-key-env",
            allow_missing_in_dry_run=True,
            dry_run=args.dry_run,
        )

    return AzureRuntimeConfig(
        base_url=_normalize_base_url(endpoint.value or ""),
        endpoint_source=endpoint.source,
        deployment=deployment.value or "",
        deployment_source=deployment.source,
        auth_mode=args.auth_mode,
        api_key=api_key.value if api_key else None,
        api_key_source=api_key.source if api_key else None,
        api_key_env_name=api_key.env_name if api_key else None,
        entra_scope=args.entra_scope,
    )


def _runtime_preview(config: AzureRuntimeConfig) -> Dict[str, Any]:
    preview: Dict[str, Any] = {
        "base_url": config.base_url,
        "endpoint_source": config.endpoint_source,
        "deployment": config.deployment,
        "deployment_source": config.deployment_source,
        "auth_mode": config.auth_mode,
    }
    if config.auth_mode == "api-key":
        preview["api_key_source"] = config.api_key_source
        preview["api_key_env_name"] = config.api_key_env_name
    else:
        preview["entra_scope"] = config.entra_scope
    return preview


def _build_auth_value(config: AzureRuntimeConfig) -> Any:
    if config.auth_mode == "api-key":
        if not config.api_key:
            env_name = config.api_key_env_name or DEFAULT_API_KEY_ENV
            _die(f"API key is not set. Set {env_name} or choose --auth-mode entra.")
        return config.api_key

    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    except ImportError:
        _die(
            "azure-identity is required for --auth-mode entra. Install with "
            "`python -m pip install azure-identity` or `uv pip install azure-identity`."
        )

    credential = DefaultAzureCredential()
    return get_bearer_token_provider(credential, config.entra_scope)


def _create_client(config: AzureRuntimeConfig):
    auth_value = _build_auth_value(config)
    try:
        from openai import OpenAI
    except ImportError:
        _die(
            "openai SDK not installed. Install with `python -m pip install openai` "
            "or `uv pip install openai`."
        )
    return OpenAI(base_url=config.base_url, api_key=auth_value)


def _create_async_client(config: AzureRuntimeConfig):
    auth_value = _build_auth_value(config)
    try:
        from openai import AsyncOpenAI
    except ImportError:
        try:
            import openai as _openai  # noqa: F401
        except ImportError:
            _die(
                "openai SDK not installed. Install with `python -m pip install openai` "
                "or `uv pip install openai`."
            )
        _die(
            "AsyncOpenAI not available in this openai SDK version. Upgrade with "
            "`python -m pip install -U openai` or `uv pip install -U openai`."
        )
    if callable(auth_value):
        token_provider = auth_value

        async def async_token_provider() -> str:
            return await asyncio.to_thread(token_provider)

        auth_value = async_token_provider
    return AsyncOpenAI(base_url=config.base_url, api_key=auth_value)


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:60] if value else "job"


def _normalize_job(job: Any, idx: int) -> Dict[str, Any]:
    if isinstance(job, str):
        prompt = job.strip()
        if not prompt:
            _die(f"Empty prompt at job {idx}")
        return {"prompt": prompt}
    if isinstance(job, dict):
        if "prompt" not in job or not str(job["prompt"]).strip():
            _die(f"Missing prompt for job {idx}")
        return job
    _die(f"Invalid job at index {idx}: expected string or object.")
    return {}  # unreachable


def _read_jobs_jsonl(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        _die(f"Input file not found: {p}")
    jobs: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item: Any
            if line.startswith("{"):
                item = json.loads(line)
            else:
                item = line
            jobs.append(_normalize_job(item, idx=line_no))
        except json.JSONDecodeError as exc:
            _die(f"Invalid JSON on line {line_no}: {exc}")
    if not jobs:
        _die("No jobs found in input file.")
    if len(jobs) > MAX_BATCH_JOBS:
        _die(f"Too many jobs ({len(jobs)}). Max is {MAX_BATCH_JOBS}.")
    return jobs


def _merge_non_null(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(dst)
    for k, v in src.items():
        if v is not None:
            merged[k] = v
    return merged


def _job_output_paths(
    *,
    out_dir: Path,
    output_format: str,
    idx: int,
    prompt: str,
    n: int,
    explicit_out: Optional[str],
    create_dir: bool = True,
) -> List[Path]:
    if create_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    ext = "." + output_format

    if explicit_out:
        base = Path(explicit_out)
        if base.suffix == "":
            base = base.with_suffix(ext)
        elif base.suffix.lstrip(".").lower() != output_format:
            _warn(
                f"Job {idx}: output extension {base.suffix} does not match output-format {output_format}."
            )
        base = out_dir / base.name
    else:
        slug = _slugify(prompt[:80])
        base = out_dir / f"{idx:03d}-{slug}{ext}"

    if n == 1:
        return [base]
    return [
        base.with_name(f"{base.stem}-{i}{base.suffix}")
        for i in range(1, n + 1)
    ]


def _extract_retry_after_seconds(exc: Exception) -> Optional[float]:
    # Best-effort: openai SDK errors vary by version. Prefer a conservative fallback.
    for attr in ("retry_after", "retry_after_seconds"):
        val = getattr(exc, attr, None)
        if isinstance(val, (int, float)) and val >= 0:
            return float(val)
    msg = str(exc)
    m = re.search(r"retry[- ]after[:= ]+([0-9]+(?:\\.[0-9]+)?)", msg, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def _is_rate_limit_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    if "ratelimit" in name or "rate_limit" in name:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def _is_transient_error(exc: Exception) -> bool:
    if _is_rate_limit_error(exc):
        return True
    name = exc.__class__.__name__.lower()
    if "timeout" in name or "timedout" in name or "tempor" in name:
        return True
    msg = str(exc).lower()
    return "timeout" in msg or "timed out" in msg or "connection reset" in msg


async def _generate_one_with_retries(
    client: Any,
    payload: Dict[str, Any],
    *,
    attempts: int,
    job_label: str,
) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return await client.images.generate(**payload)
        except Exception as exc:
            last_exc = exc
            if not _is_transient_error(exc):
                raise
            if attempt == attempts:
                raise
            sleep_s = _extract_retry_after_seconds(exc)
            if sleep_s is None:
                sleep_s = min(60.0, 2.0**attempt)
            print(
                f"{job_label} attempt {attempt}/{attempts} failed ({exc.__class__.__name__}); retrying in {sleep_s:.1f}s",
                file=sys.stderr,
            )
            await asyncio.sleep(sleep_s)
    raise last_exc or RuntimeError("unknown error")


async def _run_generate_batch(args: argparse.Namespace, config: AzureRuntimeConfig) -> int:
    jobs = _read_jobs_jsonl(args.input)
    out_dir = Path(args.out_dir)

    base_fields = _fields_from_args(args)
    base_payload = {
        "model": config.deployment,
        "n": args.n,
        "size": _effective_size(args.size, deployment=config.deployment),
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "moderation": args.moderation,
    }

    prepared_jobs = []
    for i, job in enumerate(jobs, start=1):
        prompt = str(job["prompt"]).strip()
        fields = _merge_non_null(base_fields, job.get("fields", {}))
        # Allow flat job keys as well (use_case, scene, etc.)
        fields = _merge_non_null(fields, {k: job.get(k) for k in base_fields.keys()})
        augmented = _augment_prompt_fields(args.augment, prompt, fields)

        job_payload = dict(base_payload)
        job_payload["prompt"] = augmented
        job_payload = _merge_non_null(job_payload, {k: job.get(k) for k in base_payload.keys()})
        job_payload = {k: v for k, v in job_payload.items() if v is not None}

        _validate_generate_payload(job_payload)
        effective_output_format = _normalize_output_format(job_payload.get("output_format"))
        _validate_transparency(
            job_payload.get("background"),
            effective_output_format,
            deployment=str(job_payload.get("model", config.deployment)),
        )
        if "output_format" in job_payload:
            job_payload["output_format"] = effective_output_format

        n = int(job_payload.get("n", 1))
        outputs = _job_output_paths(
            out_dir=out_dir,
            output_format=effective_output_format,
            idx=i,
            prompt=prompt,
            n=n,
            explicit_out=job.get("out"),
            create_dir=False,
        )
        prepared_jobs.append((job_payload, outputs, effective_output_format))
        if args.dry_run:
            downscaled = None
            if args.downscale_max_dim is not None:
                downscaled = [
                    str(_derive_downscale_path(p, args.downscale_suffix)) for p in outputs
                ]
            _print_request(
                {
                    "azure": _runtime_preview(config),
                    "endpoint": "/images/generations",
                    "job": i,
                    "outputs": [str(p) for p in outputs],
                    "outputs_downscaled": downscaled,
                    **job_payload,
                }
            )
    if args.dry_run:
        return 0

    _preflight_outputs(
        [path for _, outputs, _ in prepared_jobs for path in outputs],
        force=args.force,
        downscale_max_dim=args.downscale_max_dim,
        downscale_suffix=args.downscale_suffix,
    )
    client = _create_async_client(config)
    sem = asyncio.Semaphore(args.concurrency)

    any_failed = False

    async def run_job(
        i: int, payload: Dict[str, Any], outputs: List[Path], effective_output_format: str
    ) -> Tuple[int, Optional[str]]:
        nonlocal any_failed
        job_label = f"[job {i}/{len(jobs)}]"
        try:
            async with sem:
                print(f"{job_label} starting", file=sys.stderr)
                started = time.time()
                result = await _generate_one_with_retries(
                    client,
                    payload,
                    attempts=args.max_attempts,
                    job_label=job_label,
                )
                elapsed = time.time() - started
                print(f"{job_label} completed in {elapsed:.1f}s", file=sys.stderr)
            images = [item.b64_json for item in result.data]
            _decode_write_and_downscale(
                images,
                outputs,
                force=args.force,
                downscale_max_dim=args.downscale_max_dim,
                downscale_suffix=args.downscale_suffix,
                output_format=effective_output_format,
            )
            return i, None
        except Exception as exc:
            any_failed = True
            print(f"{job_label} failed: {exc}", file=sys.stderr)
            if args.fail_fast:
                raise
            return i, str(exc)

    tasks = [
        asyncio.create_task(run_job(i, payload, outputs, output_format))
        for i, (payload, outputs, output_format) in enumerate(prepared_jobs, start=1)
    ]

    try:
        await asyncio.gather(*tasks)
    except Exception:
        for t in tasks:
            if not t.done():
                t.cancel()
        raise

    return 1 if any_failed else 0


def _generate_batch(args: argparse.Namespace, config: AzureRuntimeConfig) -> None:
    exit_code = asyncio.run(_run_generate_batch(args, config))
    if exit_code:
        raise SystemExit(exit_code)


def _generate(args: argparse.Namespace, config: AzureRuntimeConfig) -> None:
    prompt = _read_prompt(args.prompt, args.prompt_file)
    prompt = _augment_prompt(args, prompt)

    payload = {
        "model": config.deployment,
        "prompt": prompt,
        "n": args.n,
        "size": _effective_size(args.size, deployment=config.deployment),
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "moderation": args.moderation,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    output_format = _normalize_output_format(args.output_format)
    _validate_transparency(args.background, output_format, deployment=config.deployment)
    if "output_format" in payload:
        payload["output_format"] = output_format
    output_paths = _build_output_paths(
        args.out,
        output_format,
        args.n,
        args.out_dir,
        create_dirs=False,
    )

    if args.dry_run:
        _print_request({"azure": _runtime_preview(config), "endpoint": "/images/generations", **payload})
        return

    _preflight_outputs(
        output_paths,
        force=args.force,
        downscale_max_dim=args.downscale_max_dim,
        downscale_suffix=args.downscale_suffix,
    )

    print(
        "Calling Azure OpenAI Image API (generation). This can take up to a couple of minutes.",
        file=sys.stderr,
    )
    started = time.time()
    client = _create_client(config)
    result = client.images.generate(**payload)
    elapsed = time.time() - started
    print(f"Generation completed in {elapsed:.1f}s.", file=sys.stderr)

    images = [item.b64_json for item in result.data]
    _decode_write_and_downscale(
        images,
        output_paths,
        force=args.force,
        downscale_max_dim=args.downscale_max_dim,
        downscale_suffix=args.downscale_suffix,
        output_format=output_format,
    )


def _edit(args: argparse.Namespace, config: AzureRuntimeConfig) -> None:
    prompt = _read_prompt(args.prompt, args.prompt_file)
    prompt = _augment_prompt(args, prompt)

    image_paths = _check_image_paths(args.image)
    mask_path = Path(args.mask) if args.mask else None
    if mask_path:
        if not mask_path.exists():
            _die(f"Mask file not found: {mask_path}")
        if mask_path.suffix.lower() != ".png":
            _warn(f"Mask should be a PNG with an alpha channel: {mask_path}")
        if mask_path.stat().st_size > MAX_IMAGE_BYTES:
            _warn(f"Mask exceeds 50MB limit: {mask_path}")

    payload = {
        "model": config.deployment,
        "prompt": prompt,
        "n": args.n,
        "size": _effective_size(args.size, deployment=config.deployment),
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "input_fidelity": args.input_fidelity,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    output_format = _normalize_output_format(args.output_format)
    _validate_transparency(args.background, output_format, deployment=config.deployment)
    if "output_format" in payload:
        payload["output_format"] = output_format
    output_paths = _build_output_paths(
        args.out,
        output_format,
        args.n,
        args.out_dir,
        create_dirs=False,
    )

    if args.dry_run:
        payload_preview = dict(payload)
        payload_preview["image"] = [str(p) for p in image_paths]
        if mask_path:
            payload_preview["mask"] = str(mask_path)
        _print_request({"azure": _runtime_preview(config), "endpoint": "/images/edits", **payload_preview})
        return

    _preflight_outputs(
        output_paths,
        force=args.force,
        downscale_max_dim=args.downscale_max_dim,
        downscale_suffix=args.downscale_suffix,
    )

    print(
        f"Calling Azure OpenAI Image API (edit) with {len(image_paths)} image(s).",
        file=sys.stderr,
    )
    started = time.time()
    client = _create_client(config)

    with _open_files(image_paths) as image_files, _open_mask(mask_path) as mask_file:
        request = dict(payload)
        request["image"] = image_files if len(image_files) > 1 else image_files[0]
        if mask_file is not None:
            request["mask"] = mask_file
        result = client.images.edit(**request)

    elapsed = time.time() - started
    print(f"Edit completed in {elapsed:.1f}s.", file=sys.stderr)
    images = [item.b64_json for item in result.data]
    _decode_write_and_downscale(
        images,
        output_paths,
        force=args.force,
        downscale_max_dim=args.downscale_max_dim,
        downscale_suffix=args.downscale_suffix,
        output_format=output_format,
    )


def _open_files(paths: List[Path]):
    return _FileBundle(paths)


def _open_mask(mask_path: Optional[Path]):
    if mask_path is None:
        return _NullContext()
    return _SingleFile(mask_path)


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _SingleFile:
    def __init__(self, path: Path):
        self._path = path
        self._handle = None

    def __enter__(self):
        self._handle = self._path.open("rb")
        return self._handle

    def __exit__(self, exc_type, exc, tb):
        if self._handle:
            try:
                self._handle.close()
            except Exception:
                pass
        return False


class _FileBundle:
    def __init__(self, paths: List[Path]):
        self._paths = paths
        self._handles: List[object] = []

    def __enter__(self):
        self._handles = [p.open("rb") for p in self._paths]
        return self._handles

    def __exit__(self, exc_type, exc, tb):
        for handle in self._handles:
            try:
                handle.close()
            except Exception:
                pass
        return False


def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--endpoint")
    parser.add_argument("--deployment")
    parser.add_argument("--auth-mode", default="api-key", choices=sorted(ALLOWED_AUTH_MODES))
    parser.add_argument("--endpoint-env")
    parser.add_argument("--deployment-env")
    parser.add_argument("--api-key-env")
    parser.add_argument("--entra-scope", default=DEFAULT_ENTRA_SCOPE)

    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--size")
    parser.add_argument("--quality", default=DEFAULT_QUALITY)
    parser.add_argument("--background")
    parser.add_argument("--output-format")
    parser.add_argument("--output-compression", type=int)
    parser.add_argument("--out", default="output.png")
    parser.add_argument("--out-dir")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--augment", dest="augment", action="store_true")
    parser.add_argument("--no-augment", dest="augment", action="store_false")
    parser.set_defaults(augment=True)

    # Prompt augmentation hints
    parser.add_argument("--use-case")
    parser.add_argument("--asset-type")
    parser.add_argument("--scene")
    parser.add_argument("--subject")
    parser.add_argument("--style")
    parser.add_argument("--composition")
    parser.add_argument("--lighting")
    parser.add_argument("--palette")
    parser.add_argument("--materials")
    parser.add_argument("--text")
    parser.add_argument("--constraints")
    parser.add_argument("--negative")

    # Post-processing (optional): generate an additional downscaled copy for fast web loading.
    parser.add_argument("--downscale-max-dim", type=int)
    parser.add_argument("--downscale-suffix", default=DEFAULT_DOWNSCALE_SUFFIX)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or edit images via Azure OpenAI v1 Image API"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_parser = subparsers.add_parser("generate", help="Create a new image")
    _add_shared_args(gen_parser)
    gen_parser.add_argument("--moderation")
    gen_parser.set_defaults(func=_generate)

    batch_parser = subparsers.add_parser(
        "generate-batch",
        help="Generate multiple prompts concurrently (JSONL input)",
    )
    _add_shared_args(batch_parser)
    batch_parser.add_argument("--moderation")
    batch_parser.add_argument("--input", required=True, help="Path to JSONL file (one job per line)")
    batch_parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    batch_parser.add_argument("--max-attempts", type=int, default=3)
    batch_parser.add_argument("--fail-fast", action="store_true")
    batch_parser.set_defaults(func=_generate_batch)

    edit_parser = subparsers.add_parser("edit", help="Edit an existing image")
    _add_shared_args(edit_parser)
    edit_parser.add_argument("--image", action="append", required=True)
    edit_parser.add_argument("--mask")
    edit_parser.add_argument("--input-fidelity")
    edit_parser.set_defaults(func=_edit)

    post_parser = subparsers.add_parser(
        "postprocess-transparent",
        help="Remove a flat key color with ImageMagick to create a transparent PNG",
    )
    post_parser.add_argument("--input", required=True)
    post_parser.add_argument("--out", required=True)
    post_parser.add_argument("--key-color", required=True)
    post_parser.add_argument("--fuzz", type=float, default=DEFAULT_TRANSPARENT_FUZZ)
    post_parser.add_argument("--trim", action="store_true")
    post_parser.add_argument("--force", action="store_true")
    post_parser.add_argument("--dry-run", action="store_true")
    post_parser.set_defaults(func=_postprocess_transparent)

    args = parser.parse_args()
    if args.command == "postprocess-transparent":
        args.func(args)
        return 0

    if args.n < 1 or args.n > 10:
        _die("--n must be between 1 and 10")
    if getattr(args, "concurrency", 1) < 1 or getattr(args, "concurrency", 1) > 25:
        _die("--concurrency must be between 1 and 25")
    if getattr(args, "max_attempts", 3) < 1 or getattr(args, "max_attempts", 3) > 10:
        _die("--max-attempts must be between 1 and 10")
    if args.output_compression is not None and not (0 <= args.output_compression <= 100):
        _die("--output-compression must be between 0 and 100")
    if args.command == "generate-batch" and not args.out_dir:
        _die("generate-batch requires --out-dir")
    if getattr(args, "downscale_max_dim", None) is not None and args.downscale_max_dim < 1:
        _die("--downscale-max-dim must be >= 1")
    if not args.entra_scope.strip():
        _die("--entra-scope cannot be empty")

    config = _resolve_runtime_config(args)
    _validate_size(args.size, deployment=config.deployment)
    _validate_quality(args.quality)
    _validate_background(args.background)

    args.func(args, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
