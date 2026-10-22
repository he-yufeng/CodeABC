from backend.services.runreqs import scan_run_requirements


def _cats(data):
    return [r["category"] for r in data["requirements"]]


def _by_category(data, category):
    return [r for r in data["requirements"] if r["category"] == category]


def test_empty_project_has_no_requirements():
    assert scan_run_requirements({})["requirements"] == []


def test_pyproject_requires_python_floor():
    files = {
        "pyproject.toml": '[project]\nname = "demo"\nrequires-python = ">=3.10"\n',
    }
    data = scan_run_requirements(files)
    reqs = _by_category(data, "python")
    assert len(reqs) == 1
    assert reqs[0]["name"] == "Python >=3.10"
    assert reqs[0]["required"] is True
    assert "pyproject.toml" in reqs[0]["detail"]


def test_pyproject_without_project_table_ignored():
    # a pyproject that is only tool config carries no floor
    files = {"pyproject.toml": '[tool.ruff]\nline-length = 88\nrequires-python = ">=3.8"\n'}
    assert _by_category(scan_run_requirements(files), "python") == []


def test_setup_cfg_python_requires():
    files = {"setup.cfg": "[options]\npython_requires = >=3.9\n"}
    reqs = _by_category(scan_run_requirements(files), "python")
    assert reqs and ">=3.9" in reqs[0]["name"]


def test_pipfile_and_runtime_txt_and_python_version():
    assert (
        _by_category(
            scan_run_requirements({"Pipfile": '[requires]\npython_version = "3.11"\n'}), "python"
        )[0]["name"]
        == "Python >=3.11"
    )
    assert (
        _by_category(scan_run_requirements({"runtime.txt": "python-3.12.1\n"}), "python")[0]["name"]
        == "Python ==3.12.1"
    )
    assert (
        _by_category(scan_run_requirements({".python-version": "3.13\n"}), "python")[0]["name"]
        == "Python ==3.13"
    )


def test_python_floor_reported_once():
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.10"\n',
        "runtime.txt": "python-3.12.1\n",
    }
    assert len(_by_category(scan_run_requirements(files), "python")) == 1


def test_node_engines_and_nvmrc():
    files = {"package.json": '{"name": "x", "engines": {"node": ">=18"}}'}
    reqs = _by_category(scan_run_requirements(files), "node")
    assert reqs and reqs[0]["name"] == "Node.js >=18"
    nvm = _by_category(scan_run_requirements({".nvmrc": "v20.11.0\n"}), "node")
    assert nvm and nvm[0]["name"] == "Node.js ==20.11.0"


def test_service_from_manifest_only_is_not_required():
    files = {"requirements.txt": "psycopg2-binary>=2.9\n"}
    reqs = _by_category(scan_run_requirements(files), "service")
    assert len(reqs) == 1
    assert reqs[0]["name"] == "PostgreSQL"
    assert reqs[0]["required"] is False


def test_service_imported_in_source_is_required():
    files = {
        "requirements.txt": "redis>=5\n",
        "app/cache.py": "import redis\n\nclient = redis.Redis()\n",
    }
    reqs = _by_category(scan_run_requirements(files), "service")
    assert reqs[0]["name"] == "Redis"
    assert reqs[0]["required"] is True


def test_js_service_package_from_require_call():
    files = {"src/db.js": 'const { Client } = require("pg")\n'}
    # pg is not in the curated map; ioredis is a manifest name, mongodb a module
    files2 = {"src/queue.js": 'import IORedis from "ioredis"\n'}
    assert _by_category(scan_run_requirements(files), "service") == []
    reqs = _by_category(scan_run_requirements(files2), "service")
    assert reqs and reqs[0]["name"] == "Redis"


def test_gpu_from_dependency_manifest():
    files = {"requirements.txt": "torch>=2.0\n"}
    reqs = _by_category(scan_run_requirements(files), "gpu")
    assert len(reqs) == 1
    assert "torch" in reqs[0]["detail"]


def test_gpu_from_cuda_source_file():
    files = {"kernels/add.cu": "__global__ void add() {}\n"}
    assert _by_category(scan_run_requirements(files), "gpu")


def test_gpu_from_cuda_device_string():
    files = {"infer.py": 'model.to("cuda:0")\n'}
    assert _by_category(scan_run_requirements(files), "gpu")


def test_no_gpu_signal_means_no_gpu_requirement():
    files = {"main.py": "import os\nprint(os.name)\n"}
    assert _by_category(scan_run_requirements(files), "gpu") == []


def test_os_windows_only_signal():
    files = {"winreg_tool.py": "import winreg\n"}
    reqs = _by_category(scan_run_requirements(files), "os")
    assert reqs and reqs[0]["name"] == "仅 Windows"


def test_os_posix_only_signal():
    files = {"lock.py": "import fcntl\n"}
    reqs = _by_category(scan_run_requirements(files), "os")
    assert reqs and reqs[0]["name"] == "仅 Linux / macOS"


def test_container_escape_hatch():
    files = {"Dockerfile": "FROM python:3.12\n"}
    reqs = _by_category(scan_run_requirements(files), "container")
    assert len(reqs) == 1
    assert reqs[0]["required"] is False
    files2 = {"deploy/docker-compose.yml": "services: {}\n"}
    assert _by_category(scan_run_requirements(files2), "container")


def test_ordering_python_before_service_before_container():
    files = {
        "Dockerfile": "FROM python:3.12\n",
        "requirements.txt": "redis\n",
        "pyproject.toml": '[project]\nrequires-python = ">=3.10"\n',
    }
    cats = _cats(scan_run_requirements(files))
    assert cats == ["python", "service", "container"]
