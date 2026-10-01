from __future__ import annotations

import base64
import asyncio
import importlib.util
import inspect
import json
import os
import re
import secrets
import shlex
from email.parser import BytesParser
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree

import openai
import httpx2 as httpx
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "azure-imagegen" / "scripts" / "image_gen.py"
SKILL_PATH = REPO_ROOT / "skills" / "azure-imagegen" / "SKILL.md"
OPENAI_YAML_PATH = REPO_ROOT / "skills" / "azure-imagegen" / "agents" / "openai.yaml"
PLUGIN_MANIFEST_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)
@pytest.fixture(autouse=True)
def isolate_model_environment(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_IMAGE_MODEL", raising=False)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_cli_with_env(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _write_png(path: Path) -> None:
    path.write_bytes(ONE_PIXEL_PNG)


def _run_generate(deployment: str, *args: str) -> subprocess.CompletedProcess[str]:
    return _run_cli(
        "generate",
        "--endpoint",
        "https://example.openai.azure.com",
        "--deployment",
        deployment,
        "--prompt",
        "smoke test",
        *args,
        "--dry-run",
    )


def _load_skill_frontmatter() -> dict:
    raw = SKILL_PATH.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    return yaml.safe_load(match.group(1))


def test_plugin_manifest_references_existing_assets() -> None:
    manifest = json.loads(PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["name"] == "azure-imagegen"
    assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"])
    assert manifest["skills"] == "./skills/"

    interface = manifest["interface"]
    assert len(interface["defaultPrompt"]) == 3

    asset_keys = ["composerIcon", "logo"]
    asset_paths = [interface[key] for key in asset_keys] + interface["screenshots"]
    for rel_path in asset_paths:
        assert rel_path.startswith("./")
        assert (REPO_ROOT / rel_path.removeprefix("./")).is_file()


def test_skill_metadata_matches_plugin_packaging() -> None:
    frontmatter = _load_skill_frontmatter()
    openai_yaml = yaml.safe_load(OPENAI_YAML_PATH.read_text(encoding="utf-8"))
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    assert frontmatter["name"] == "azure-imagegen"
    assert "Generate, edit, and batch-create images" in frontmatter["description"]
    assert "$azure-imagegen" in openai_yaml["interface"]["default_prompt"]
    assert "gpt-image-1.5" in skill_text
    assert "gpt-image-2.5-sunburst" in skill_text
    assert "gpt-image-2.5-flare" in skill_text
    assert "--image-model" in skill_text


def test_portable_and_legacy_metadata_and_marketplace_agree() -> None:
    portable = json.loads((REPO_ROOT / "plugin.json").read_text(encoding="utf-8"))
    legacy = json.loads(PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8"))
    package = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert portable["version"] == legacy["version"] == package["version"] == "0.3.0"
    assert portable["extensions"]["com.openai"]["interface"] == legacy["interface"]
    for key in ("name", "description", "author", "homepage", "repository", "license", "keywords"):
        assert portable[key] == legacy[key]
    assert portable["author"]["name"] == legacy["interface"]["developerName"] == "DangerMouseUK"
    assert package["authors"] == [{"name": "DangerMouseUK"}]
    assert portable["repository"] == "https://github.com/dangermouseuk/azure-imagegen"
    assert "skills" not in portable  # Portable components are discovered at fixed root paths.
    assert package["license"] == "MIT"
    assert package["license-files"] == ["LICENSE"]

    catalog = json.loads((REPO_ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    assert catalog["name"] == "dangermouseuk"
    assert catalog["interface"]["displayName"] == "DangerMouseUK"
    assert len(catalog["plugins"]) == 1
    entry = catalog["plugins"][0]
    assert entry["name"] == portable["name"]
    assert entry["source"]["source"] == "local"
    assert (REPO_ROOT / entry["source"]["path"]).resolve() == REPO_ROOT.resolve()
    assert entry["category"] == legacy["interface"]["category"]

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "codex plugin marketplace add dangermouseuk/azure-imagegen --ref main" in readme
    assert "codex plugin add azure-imagegen@dangermouseuk" in readme
    assert "codex plugin marketplace upgrade dangermouseuk" in readme


def test_generate_help_smoke() -> None:
    result = _run_cli("--help")

    assert result.returncode == 0
    assert "generate-batch" in result.stdout
    assert "edit" in result.stdout
    assert "postprocess-transparent" in result.stdout


def test_generate_dry_run_does_not_create_output_dir(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated"

    result = _run_cli(
        "generate",
        "--endpoint",
        "https://example.openai.azure.com",
        "--deployment",
        "gpt-image-prod",
        "--prompt",
        "smoke test",
        "--out-dir",
        str(out_dir),
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert not out_dir.exists()
    payload = json.loads(result.stdout)
    assert payload["endpoint"] == "/images/generations"


def test_edit_dry_run_does_not_create_output_dir(tmp_path: Path) -> None:
    image_path = tmp_path / "input.png"
    out_dir = tmp_path / "edited"
    _write_png(image_path)

    result = _run_cli(
        "edit",
        "--endpoint",
        "https://example.openai.azure.com",
        "--deployment",
        "gpt-image-prod",
        "--image",
        str(image_path),
        "--prompt",
        "change only the background",
        "--out-dir",
        str(out_dir),
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert not out_dir.exists()
    payload = json.loads(result.stdout)
    assert payload["endpoint"] == "/images/edits"
    assert payload["image"] == [str(image_path)]


def test_generate_batch_dry_run_does_not_create_output_dir(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.jsonl"
    out_dir = tmp_path / "batch"
    input_path.write_text('{"prompt": "batch smoke test"}\n', encoding="utf-8")

    result = _run_cli(
        "generate-batch",
        "--endpoint",
        "https://example.openai.azure.com",
        "--deployment",
        "gpt-image-prod",
        "--input",
        str(input_path),
        "--out-dir",
        str(out_dir),
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert not out_dir.exists()
    payload = json.loads(result.stdout)
    assert payload["endpoint"] == "/images/generations"
    assert payload["outputs"] == [str(out_dir / "001-batch-smoke-test.png")]


def test_gpt_image_2_omits_default_size_for_routing() -> None:
    result = _run_generate("gpt-image-2-prod")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["model"] == "gpt-image-2-prod"
    assert "size" not in payload


@pytest.mark.parametrize("size", ["3840x2160", "2160x3840", "1280x720"])
def test_gpt_image_2_accepts_4k_and_custom_aligned_sizes(size: str) -> None:
    result = _run_generate("gpt-image-2-prod", "--size", size)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["size"] == size


def test_gpt_image_2_rejects_too_small_size() -> None:
    result = _run_generate("gpt-image-2-prod", "--size", "800x800")

    assert result.returncode == 1
    assert "at least 655,360" in result.stderr


def test_gpt_image_2_rejects_unaligned_size() -> None:
    result = _run_generate("gpt-image-2-prod", "--size", "1025x1024")

    assert result.returncode == 1
    assert "multiple of 16" in result.stderr


def test_gpt_image_2_rejects_over_budget_size() -> None:
    result = _run_generate("gpt-image-2-prod", "--size", "3840x3840")

    assert result.returncode == 1
    assert "must not exceed 8,294,400" in result.stderr


def test_legacy_deployment_still_rejects_gpt_image_2_custom_size() -> None:
    result = _run_generate("gpt-image-prod", "--size", "3840x2160")

    assert result.returncode == 1
    assert "size must be one of" in result.stderr


def test_gpt_image_2_accepts_explicit_preview_transparency() -> None:
    result = _run_generate(
        "gpt-image-2-prod",
        "--background",
        "transparent",
        "--output-format",
        "png",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["background"] == "transparent"
    assert "preview feature" in result.stderr
    assert "Azure deployment" in result.stderr
    assert "postprocess-transparent" in result.stderr


def test_legacy_deployment_accepts_transparent_background() -> None:
    result = _run_generate(
        "gpt-image-prod",
        "--background",
        "transparent",
        "--output-format",
        "png",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["background"] == "transparent"
    assert payload["output_format"] == "png"


def test_postprocess_transparent_dry_run_prints_magick_command(tmp_path: Path) -> None:
    image_path = tmp_path / "keyed.png"
    out_path = tmp_path / "transparent.png"
    _write_png(image_path)

    result = _run_cli(
        "postprocess-transparent",
        "--input",
        str(image_path),
        "--out",
        str(out_path),
        "--key-color",
        "#00FF00",
        "--trim",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert not out_path.exists()
    payload = json.loads(result.stdout)
    command = payload["command"]
    assert Path(command[0]).name.lower().startswith("magick")
    assert "-transparent" in command
    assert "#00FF00" in command
    assert "-trim" in command
    assert "+repage" in command


def test_postprocess_transparent_missing_magick_is_clear(tmp_path: Path) -> None:
    image_path = tmp_path / "keyed.png"
    out_path = tmp_path / "transparent.png"
    _write_png(image_path)
    env = {**os.environ, "PATH": ""}

    result = _run_cli_with_env(
        "postprocess-transparent",
        "--input",
        str(image_path),
        "--out",
        str(out_path),
        "--key-color",
        "#00FF00",
        env=env,
    )

    assert result.returncode == 1
    assert "ImageMagick `magick` was not found on PATH" in result.stderr


def test_postprocess_transparent_requires_png_output(tmp_path: Path) -> None:
    image_path = tmp_path / "keyed.png"
    _write_png(image_path)

    result = _run_cli(
        "postprocess-transparent",
        "--input",
        str(image_path),
        "--out",
        str(tmp_path / "transparent.jpg"),
        "--key-color",
        "#00FF00",
        "--dry-run",
    )

    assert result.returncode == 1
    assert "output must be a PNG" in result.stderr


@pytest.fixture
def mocked_image_api(monkeypatch):
    spec = importlib.util.spec_from_file_location("image_gen_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "offline-test-key")
    requests = []
    clients = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"created": 0, "data": [{"b64_json": base64.b64encode(ONE_PIXEL_PNG).decode()}]},
        )

    sync_client = openai.OpenAI
    async_client = openai.AsyncOpenAI
    transport = httpx.MockTransport(respond)

    def create_sync(**kwargs):
        client = sync_client(**kwargs, http_client=httpx.Client(transport=transport))
        clients.append(client)
        return client

    def create_async(**kwargs):
        client = async_client(**kwargs, http_client=httpx.AsyncClient(transport=transport))
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "OpenAI", create_sync)
    monkeypatch.setattr(openai, "AsyncOpenAI", create_async)
    yield module, requests
    for client in clients:
        result = client.close()
        if inspect.isawaitable(result):
            asyncio.run(result)


def _live_cli_args(command: str, tmp_path: Path) -> list[str]:
    args = [
        command,
        "--endpoint", "https://example.openai.azure.com",
        "--deployment", "gpt-image-prod",
        "--prompt", "offline request test",
        "--downscale-max-dim", "1",
    ]
    out_dir = tmp_path / "output"
    if command == "generate-batch":
        jobs = tmp_path / "jobs.jsonl"
        jobs.write_text(
            '{"prompt": "first", "out": "first.png"}\n'
            '{"prompt": "second", "out": "result.png"}\n', encoding="utf-8"
        )
        args.extend(["--input", str(jobs), "--out-dir", str(out_dir)])
    else:
        args.extend(["--out", str(out_dir / "result.png")])
    if command == "edit":
        image = tmp_path / "input.png"
        _write_png(image)
        args.extend(["--image", str(image), "--input-fidelity", "high"])
    return args


@pytest.mark.parametrize("command", ["generate", "edit", "generate-batch"])
@pytest.mark.parametrize("env_name", ["AZURE_OPENAI_API_KEY", "IMAGE_TEST_CREDENTIAL"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_credentials_are_never_written_to_cli_output(
    mocked_image_api, monkeypatch, tmp_path: Path, capsys,
    command: str, env_name: str, dry_run: bool,
) -> None:
    module, requests = mocked_image_api
    credential = secrets.token_hex(32)
    monkeypatch.setenv(env_name, credential)
    args = _live_cli_args(command, tmp_path)
    if env_name != "AZURE_OPENAI_API_KEY":
        args.extend(["--api-key-env", env_name])
    if dry_run:
        args.append("--dry-run")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args])

    assert module.main() == 0

    output = capsys.readouterr()
    assert credential not in output.out
    assert credential not in output.err
    if dry_run:
        assert requests == []
        assert not (tmp_path / "output").exists()
        preview, _ = json.JSONDecoder().raw_decode(output.out)
        assert preview["azure"]["api_key_env_name"] == env_name
        assert preview["azure"]["api_key_source"] == f"env:{env_name}"
    else:
        assert len(requests) == (2 if command == "generate-batch" else 1)
        assert all(request.headers["authorization"] == f"Bearer {credential}" for request in requests)


@pytest.mark.parametrize("dry_run", [False, True])
def test_missing_credential_messages_only_show_the_environment_name(
    mocked_image_api, monkeypatch, tmp_path: Path, capsys, dry_run: bool,
) -> None:
    module, requests = mocked_image_api
    env_name = "IMAGE_TEST_CREDENTIAL"
    monkeypatch.delenv(env_name, raising=False)
    args = _live_cli_args("generate", tmp_path) + ["--api-key-env", env_name]
    if dry_run:
        args.append("--dry-run")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args])

    if dry_run:
        assert module.main() == 0
    else:
        with pytest.raises(SystemExit) as error:
            module.main()
        assert error.value.code == 1

    output = capsys.readouterr()
    assert f"api key is not set. Set {env_name}." in output.err
    if dry_run:
        preview = json.loads(output.out)
        assert preview["azure"]["api_key_source"] == f"missing:{env_name}"
    assert requests == []
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("command", ["generate", "edit", "generate-batch"])
@pytest.mark.parametrize("existing_name", ["result.png", "result-web.png"])
def test_existing_outputs_stop_all_api_calls(
    mocked_image_api, monkeypatch, tmp_path: Path, capsys, command: str, existing_name: str
) -> None:
    module, requests = mocked_image_api
    args = _live_cli_args(command, tmp_path)
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    existing = out_dir / existing_name
    existing.write_bytes(b"keep existing file")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args])

    with pytest.raises(SystemExit) as error:
        module.main()

    assert error.value.code == 1
    assert "Output already exists" in capsys.readouterr().err
    assert requests == []
    assert existing.read_bytes() == b"keep existing file"
    assert sorted(path.name for path in out_dir.iterdir()) == [existing_name]


@pytest.mark.parametrize("command", ["generate", "edit", "generate-batch"])
def test_force_overwrites_with_supported_sdk(
    mocked_image_api, monkeypatch, tmp_path: Path, command: str
) -> None:
    module, requests = mocked_image_api
    args = _live_cli_args(command, tmp_path)
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    (out_dir / "result.png").write_bytes(b"old original")
    (out_dir / "result-web.png").write_bytes(b"old downscaled")
    if command != "edit":
        args.extend(["--moderation", "low"])
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, "--force"])

    assert module.main() == 0
    assert len(requests) == (2 if command == "generate-batch" else 1)
    assert all(request.headers["authorization"] == "Bearer offline-test-key" for request in requests)
    assert (out_dir / "result.png").read_bytes() == ONE_PIXEL_PNG
    assert (out_dir / "result-web.png").read_bytes() != b"old downscaled"
    if command != "edit":
        assert all(json.loads(request.content)["moderation"] == "low" for request in requests)
    else:
        assert requests[0].url.path == "/openai/v1/images/edits"


@pytest.mark.parametrize("force", [False, True])
def test_overlapping_batch_outputs_rejected_before_requests(
    mocked_image_api, monkeypatch, tmp_path: Path, capsys, force: bool
) -> None:
    module, requests = mocked_image_api
    args = _live_cli_args("generate-batch", tmp_path)
    (tmp_path / "jobs.jsonl").write_text(
        '{"prompt": "first", "out": "result.png"}\n'
        '{"prompt": "second", "out": "result-web.png"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, *(["--force"] if force else [])])

    with pytest.raises(SystemExit):
        module.main()

    assert "Output paths overlap" in capsys.readouterr().err
    assert requests == []
    assert not (tmp_path / "output").exists()


def test_all_numbered_outputs_checked_before_request(
    mocked_image_api, monkeypatch, tmp_path: Path
) -> None:
    module, requests = mocked_image_api
    args = _live_cli_args("generate", tmp_path)
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    (out_dir / "result-2.png").write_bytes(b"keep second image")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, "--n", "2"])

    with pytest.raises(SystemExit):
        module.main()

    assert requests == []
    assert not (out_dir / "result-1.png").exists()
    assert (out_dir / "result-2.png").read_bytes() == b"keep second image"


def test_edit_rejects_generation_only_moderation(tmp_path: Path) -> None:
    image = tmp_path / "input.png"
    _write_png(image)
    result = _run_cli("edit", "--image", str(image), "--moderation", "low", "--dry-run")

    assert result.returncode == 2
    assert "unrecognized arguments: --moderation low" in result.stderr
    assert "--moderation" not in _run_cli("edit", "--help").stdout
    assert "--moderation" in _run_cli("generate", "--help").stdout
    assert "--moderation" in _run_cli("generate-batch", "--help").stdout


@pytest.mark.parametrize("command", ["generate", "edit", "generate-batch"])
def test_entra_uses_supported_token_provider(
    mocked_image_api, monkeypatch, tmp_path: Path, command: str
) -> None:
    module, requests = mocked_image_api
    identity = ModuleType("azure.identity")
    identity.DefaultAzureCredential = lambda: object()
    identity.get_bearer_token_provider = lambda credential, scope: lambda: "offline-token"
    azure = ModuleType("azure")
    azure.identity = identity
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.identity", identity)
    args = _live_cli_args(command, tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, "--auth-mode", "entra"])

    assert module.main() == 0
    assert len(requests) == (2 if command == "generate-batch" else 1)
    assert all(request.headers["authorization"] == "Bearer offline-token" for request in requests)


def test_installation_graphic_contains_complete_marketplace_json() -> None:
    root = ElementTree.parse(REPO_ROOT / "assets" / "screenshot-install.svg").getroot()
    code = root.find(".//{http://www.w3.org/2000/svg}text[@id='marketplace-json']")
    catalog = json.loads("\n".join(line.text for line in code))
    committed_catalog = json.loads(
        (REPO_ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
    )
    assert catalog == committed_catalog


IMAGE_MODELS = [
    "gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5", "gpt-image-2",
    "gpt-image-2.5-sunburst", "gpt-image-2.5-flare",
]
MODERN_IMAGE_MODELS = IMAGE_MODELS[3:]


@pytest.mark.parametrize("model", IMAGE_MODELS)
def test_model_inference_recognizes_specific_names_and_snapshots(model: str) -> None:
    result = _run_generate(f"studio-{model.upper()}-2026-09-08")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["azure"]["image_model"] == model
    assert payload["azure"]["image_model_source"] == "inferred:deployment"
    assert payload["model"] == f"studio-{model.upper()}-2026-09-08"
    assert payload["quality"] == "high"
    assert payload["output_format"] == "png"
    assert ("size" in payload) == (model not in MODERN_IMAGE_MODELS)


def test_unknown_model_retains_legacy_defaults_with_guidance() -> None:
    result = _run_generate("images-prod")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["azure"]["image_model"] == "legacy"
    assert payload["size"] == "1024x1024"
    assert "Cannot infer" in result.stderr
    assert "--image-model" in result.stderr


@pytest.mark.parametrize(
    "cli_model,env_model,deployment,expected,source",
    [
        (None, "gpt-image-2.5-flare", "images-prod", "gpt-image-2.5-flare",
         "env:AZURE_OPENAI_IMAGE_MODEL"),
        ("gpt-image-2.5-sunburst", "gpt-image-1", "images-prod", "gpt-image-2.5-sunburst",
         "flag:--image-model"),
        ("auto", "gpt-image-1", "gpt-image-2.5-flare-2026-09-08", "gpt-image-2.5-flare",
         "inferred:deployment"),
        (None, "auto", "gpt-image-2-prod", "gpt-image-2", "inferred:deployment"),
        (None, "", "gpt-image-2-prod", "gpt-image-2", "inferred:deployment"),
        (None, "   ", "gpt-image-2-prod", "gpt-image-2", "inferred:deployment"),
    ],
)
def test_model_selection_precedence(cli_model, env_model, deployment, expected, source) -> None:
    args = [
        "generate", "--endpoint", "https://example.openai.azure.com",
        "--deployment", deployment, "--prompt", "test", "--dry-run",
    ]
    if cli_model is not None:
        args.extend(["--image-model", cli_model])
    result = _run_cli_with_env(
        *args, env={**os.environ, "AZURE_OPENAI_IMAGE_MODEL": env_model},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["azure"]["image_model"] == expected
    assert payload["azure"]["image_model_source"] == source
    assert payload["model"] == deployment


@pytest.mark.parametrize("model", IMAGE_MODELS[-2:])
@pytest.mark.parametrize("quality", ["low", "medium", "high", "xhigh", "max", "auto"])
def test_image_25_accepts_all_documented_qualities_and_native_transparency(model, quality) -> None:
    result = _run_generate(
        "images-prod", "--image-model", model, "--quality", quality,
        "--background", "transparent", "--size", "auto",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["model"] == "images-prod"
    assert payload["quality"] == quality
    assert payload["size"] == "auto"
    assert payload["background"] == "transparent"
    assert payload["output_format"] == "png"
    assert "preview feature" not in result.stderr


@pytest.mark.parametrize("model", IMAGE_MODELS[:4])
@pytest.mark.parametrize("quality", ["xhigh", "max", "auto"])
def test_earlier_models_reject_undocumented_azure_qualities(model, quality) -> None:
    result = _run_generate(model, "--quality", quality)
    assert result.returncode == 1
    assert "quality for" in result.stderr


@pytest.mark.parametrize("model", MODERN_IMAGE_MODELS)
@pytest.mark.parametrize("size", ["auto", "1024x640", "1536x512", "3840x2160", "2160x3840"])
def test_modern_sizes_accept_auto_and_valid_boundaries(model, size) -> None:
    result = _run_generate(model, "--size", size)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["size"] == size
    assert ("experimental" in result.stderr) == (
        model in IMAGE_MODELS[-2:] and size in ("3840x2160", "2160x3840")
    )


@pytest.mark.parametrize(
    "size,message",
    [
        ("0x1024", "greater than zero"),
        ("1025x1024", "multiple of 16"),
        ("4096x1024", "must not exceed 3,840"),
        ("3072x768", "aspect ratio"),
        ("800x800", "at least 655,360"),
        ("3840x3840", "must not exceed 8,294,400"),
    ],
)
def test_invalid_sizes_stop_before_requests(mocked_image_api, monkeypatch, tmp_path, capsys, size, message):
    module, requests = mocked_image_api
    args = _live_cli_args("generate", tmp_path)
    args.extend(["--image-model", "gpt-image-2.5-flare", "--size", size])
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args])
    with pytest.raises(SystemExit):
        module.main()
    assert message in capsys.readouterr().err
    assert requests == []
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("command", ["generate", "edit", "generate-batch"])
@pytest.mark.parametrize(
    "flags,message",
    [
        (["--output-format", "webp"], "does not support WEBP"),
        (["--output-format", "jpeg", "--background", "transparent"], "requires output-format png"),
        (["--output-compression", "80"], "only supported for JPEG"),
        (["--output-compression", "-1"], "between 0 and 100"),
        (["--n", "11"], "between 1 and 10"),
    ],
)
def test_invalid_options_stop_all_requests(
    mocked_image_api, monkeypatch, tmp_path, capsys, command, flags, message
):
    module, requests = mocked_image_api
    args = _live_cli_args(command, tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, *flags])
    with pytest.raises(SystemExit):
        module.main()
    assert message in capsys.readouterr().err
    assert requests == []
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("compression", [0, 100])
def test_jpg_alias_and_compression_boundaries(compression):
    result = _run_generate(
        "gpt-image-2.5-flare", "--output-format", "jpg",
        "--output-compression", str(compression), "--out", "test.jpeg",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["output_format"] == "jpeg"
    assert payload["output_compression"] == compression


@pytest.mark.parametrize("model", IMAGE_MODELS)
def test_edit_fidelity_is_model_aware(mocked_image_api, monkeypatch, tmp_path, capsys, model):
    module, requests = mocked_image_api
    args = _live_cli_args("edit", tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, "--image-model", model])
    if model in ("gpt-image-2", "gpt-image-1-mini"):
        with pytest.raises(SystemExit):
            module.main()
        assert "omit --input-fidelity" in capsys.readouterr().err
        assert requests == []
        assert not (tmp_path / "output").exists()
    else:
        assert module.main() == 0
        assert len(requests) == 1


@pytest.mark.parametrize("model", ["gpt-image-2", "gpt-image-1-mini"])
def test_edit_omits_unsupported_fidelity(mocked_image_api, monkeypatch, tmp_path, model):
    module, requests = mocked_image_api
    args = _live_cli_args("edit", tmp_path)
    fidelity_flag = args.index("--input-fidelity")
    del args[fidelity_flag:fidelity_flag + 2]
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, "--image-model", model])
    assert module.main() == 0
    assert b"input_fidelity" not in requests[0].content


def _request_fields(request):
    if request.headers["content-type"].startswith("application/json"):
        return json.loads(request.content)
    message = BytesParser().parsebytes(
        f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode() + request.content
    )
    return {
        part.get_param("name", header="content-disposition"): part.get_payload(decode=True).decode()
        for part in message.walk()
        if part.get_content_disposition() == "form-data" and part.get_filename() is None
    }


@pytest.mark.parametrize("command", ["generate", "edit", "generate-batch"])
@pytest.mark.parametrize("model", IMAGE_MODELS[-2:])
def test_image_25_real_sdk_serialization(mocked_image_api, monkeypatch, tmp_path, command, model):
    module, requests = mocked_image_api
    args = _live_cli_args(command, tmp_path)
    args.extend([
        "--image-model", model, "--quality", "max", "--size", "auto",
        "--background", "transparent",
    ])
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args])
    assert module.main() == 0
    assert len(requests) == (2 if command == "generate-batch" else 1)
    for request in requests:
        fields = _request_fields(request)
        assert fields["model"] == "gpt-image-prod"  # Azure deployment is preserved.
        assert fields["quality"] == "max"
        assert fields["size"] == "auto"
        assert fields["background"] == "transparent"
        assert fields["output_format"] == "png"
        assert "image_model" not in fields
        assert "azure" not in fields


def test_batch_overrides_profiles_and_deployments_before_defaults(
    mocked_image_api, monkeypatch, tmp_path
):
    module, requests = mocked_image_api
    args = _live_cli_args("generate-batch", tmp_path)
    monkeypatch.setenv("AZURE_OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
    (tmp_path / "jobs.jsonl").write_text(
        json.dumps({"prompt": "legacy", "image_model": "gpt-image-1", "out": "legacy.png"}) + "\n"
        + json.dumps({
            "prompt": "modern", "model": "images-precise", "image_model": "gpt-image-2.5-sunburst",
            "quality": "xhigh", "out": "modern.png",
        }) + "\n"
        + json.dumps({
            "prompt": "inferred", "model": "gpt-image-2.5-flare-2026-09-08",
            "image_model": "auto", "out": "inferred.png",
        }) + "\n"
        + json.dumps({"prompt": "cli profile", "out": "cli.png"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT_PATH), *args, "--image-model", "gpt-image-2",
    ])
    assert module.main() == 0
    payloads = [json.loads(request.content) for request in requests]
    assert len(payloads) == 4
    assert sum("size" in payload for payload in payloads) == 1
    precise = next(payload for payload in payloads if payload["model"] == "images-precise")
    assert precise["quality"] == "xhigh"
    assert "size" not in precise
    assert all("image_model" not in payload for payload in payloads)


@pytest.mark.parametrize(
    "override,message",
    [
        ({"quality": "max", "image_model": "gpt-image-1"}, "quality for"),
        ({"size": "3840x3840"}, "8,294,400"),
        ({"background": "transparent", "output_format": "jpeg"}, "requires output-format png"),
        ({"output_format": "webp"}, "does not support WEBP"),
        ({"output_compression": 70}, "only supported for JPEG"),
        ({"image_model": "unknown"}, "Unknown image model"),
        ({"image_model": ["gpt-image-2"]}, "must be a model identifier"),
        ({"n": 1.5}, "must be an integer"),
        ({"size": 1024}, "must be a WIDTHxHEIGHT"),
    ],
)
def test_invalid_later_batch_job_prevents_all_requests(
    mocked_image_api, monkeypatch, tmp_path, capsys, override, message
):
    module, requests = mocked_image_api
    args = _live_cli_args("generate-batch", tmp_path)
    (tmp_path / "jobs.jsonl").write_text(
        json.dumps({"prompt": "valid", "out": "first.png"}) + "\n"
        + json.dumps({"prompt": "invalid", "out": "second.png", **override}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT_PATH), *args, "--image-model", "gpt-image-2.5-flare",
    ])
    with pytest.raises(SystemExit):
        module.main()
    assert message in capsys.readouterr().err
    assert requests == []
    assert not (tmp_path / "output").exists()


def test_cli_graphic_matches_an_actual_dry_run() -> None:
    root = ElementTree.parse(REPO_ROOT / "assets/screenshot-cli.svg").getroot()
    command = root.find(".//{http://www.w3.org/2000/svg}text[@id='cli-command']")
    args = shlex.split(" ".join(line.text.rstrip("`").strip() for line in command))
    result = _run_cli(*args[2:])  # Use this platform's Python and script path.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    payload.pop("azure")
    payload.pop("endpoint")
    code = root.find(".//{http://www.w3.org/2000/svg}text[@id='request-json']")
    assert json.loads("\n".join(line.text for line in code)) == payload
