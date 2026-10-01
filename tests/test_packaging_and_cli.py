from __future__ import annotations

import base64
import asyncio
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree

import openai
from openai import _base_client
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
# Use the same HTTP transport as the installed SDK (1.x/2.x or 3.x).
httpx = getattr(_base_client, "httpx2", None) or _base_client.httpx


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
    assert "gpt-image-1.5" not in skill_text


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


def test_gpt_image_2_allows_over_budget_size_with_warning() -> None:
    result = _run_generate("gpt-image-2-prod", "--size", "3840x3840")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["size"] == "3840x3840"
    assert "Azure may resize the final image to fit" in result.stderr


def test_legacy_deployment_still_rejects_gpt_image_2_custom_size() -> None:
    result = _run_generate("gpt-image-prod", "--size", "3840x2160")

    assert result.returncode == 1
    assert "size must be one of" in result.stderr


def test_gpt_image_2_rejects_transparent_background() -> None:
    result = _run_generate(
        "gpt-image-2-prod",
        "--background",
        "transparent",
        "--output-format",
        "png",
    )

    assert result.returncode == 1
    assert "GPT-image-2 does not support background=transparent" in result.stderr
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


def test_entra_batch_uses_awaitable_token_provider(mocked_image_api, monkeypatch, tmp_path: Path) -> None:
    module, requests = mocked_image_api
    identity = ModuleType("azure.identity")
    identity.DefaultAzureCredential = lambda: object()
    identity.get_bearer_token_provider = lambda credential, scope: lambda: "offline-token"
    azure = ModuleType("azure")
    azure.identity = identity
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.identity", identity)
    args = _live_cli_args("generate-batch", tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *args, "--auth-mode", "entra"])

    assert module.main() == 0
    assert len(requests) == 2
    assert all(request.headers["authorization"] == "Bearer offline-token" for request in requests)


def test_installation_graphic_contains_complete_marketplace_json() -> None:
    root = ElementTree.parse(REPO_ROOT / "assets" / "screenshot-install.svg").getroot()
    code = root.find(".//{http://www.w3.org/2000/svg}text[@id='marketplace-json']")
    catalog = json.loads("\n".join(line.text for line in code))
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    documented_catalog = json.loads(re.search(r"```json\n(.*?)\n```", readme, re.DOTALL).group(1))

    assert catalog["plugins"] == documented_catalog["plugins"]
