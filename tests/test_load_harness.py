"""The load harness must not be able to report a number it did not earn.

A benchmark can fail without raising. It can authenticate with a JSON body and
get 422 for every request, time the refusals, and print a confident throughput
figure; or it can record its own environment as the server's state and describe a
demo-data run as a real-data run. Both produce output that looks like a result.

These tests pin the properties that stop that, without running a load test.
"""
import ast
import pathlib

LOAD_DIR = pathlib.Path(__file__).resolve().parent / "load"

LOCUSTFILE = LOAD_DIR / "locustfile.py"
RUNNER = LOAD_DIR / "run_load_test.py"
REQ_FILE = LOAD_DIR / "requirements.txt"


def _source(path: pathlib.Path) -> str:
    return path.read_text()


def test_locust_is_not_in_production_requirements():
    """Locust ships a web server; it must not ride in the application image."""
    prod = pathlib.Path(__file__).resolve().parents[1] / "backend" / "requirements.txt"
    body = prod.read_text().lower()
    assert "locust" not in body
    assert "flask" not in body, "locust's dev server dependency leaked into prod"


def test_locust_has_its_own_requirements_file():
    assert "locust" in REQ_FILE.read_text().lower()


def test_login_uses_form_encoding_not_json():
    """Login is OAuth2PasswordRequestForm. JSON yields 422 for every request."""
    src = _source(LOCUSTFILE)
    tree = ast.parse(src)
    login_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
        and any(
            isinstance(a, ast.Constant) and "login" in str(a.value)
            for a in node.args
        )
    ]
    assert login_calls, "no login call found to check"
    for call in login_calls:
        kwargs = {k.arg for k in call.keywords}
        assert "data" in kwargs, "login must send form data"
        assert "json" not in kwargs, "login must not send JSON"


def test_failed_login_aborts_rather_than_measuring_401s():
    src = _source(LOCUSTFILE)
    assert "login failed" in src
    assert "SystemExit" in src or "EnvironmentError" in src


def test_no_default_host():
    """A default target is how a load test ends up hitting an environment."""
    src = _source(RUNNER)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument":
            if any(
                isinstance(a, ast.Constant) and a.value == "--host" for a in node.args
            ):
                assert any(
                    kw.arg == "required" and getattr(kw.value, "value", False) is True
                    for kw in node.keywords
                ), "--host must be required"
                return
    raise AssertionError("--host argument not found")


def test_demo_mode_is_probed_not_inherited():
    """Recording the generator's env describes the wrong process."""
    src = _source(RUNNER)
    assert "detect_demo_mode" in src
    assert 'os.getenv("ENABLE_DEMO_MODE"' not in src, (
        "demo mode must be read from the server, not this process's environment"
    )


def test_deployment_shape_is_recorded_with_the_numbers():
    """Percentiles quoted without context are the thing this guards against."""
    src = _source(RUNNER)
    for key in ("workers", "cache", "resource_limits", "demo_mode"):
        assert f'"{key}"' in src, f"deployment shape omits {key}"


def test_zero_successful_requests_is_a_failure():
    """No successes is a broken run, not a fast one."""
    src = _source(RUNNER)
    assert "Zero successful requests" in src


def test_probe_precedes_load_generation():
    """Refuse before generating load, not after."""
    src = _source(RUNNER)
    assert src.index("/health") < src.index('"locust"'), (
        "target probe must run before the locust subprocess"
    )


def test_every_endpoint_in_the_scenario_exists():
    """A 404 in a load profile is a typo that still produces a latency number."""
    src = _source(LOCUSTFILE)
    for path in (
        "/health",
        "/api/v1/parcels/",
        "/api/v1/properties/hero",
        "/api/v1/precinct/buildings",
        "/api/v1/verification/cases",
        "/api/v1/datasources/status",
    ):
        assert f'"{path}"' in src, f"{path} not exercised"


def test_readme_states_the_deployment_and_the_caveats():
    body = (LOAD_DIR / "README.md").read_text()
    assert "one worker" in body.lower() or "single worker" in body.lower()
    assert "not a capacity claim" in body.lower()
    assert "NullPool" in body
    # The trialled-and-reverted result has to stay visible, or the next reader
    # will repeat the experiment and rediscover it.
    assert "reverted" in body.lower()