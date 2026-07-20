import pytest

from app.validation import validate_arguments, validate_ports, validate_targets


# --- targets ---

@pytest.mark.parametrize("targets", [
    "127.0.0.1",
    "192.168.1.0/24",
    "192.168.1.1-127",
    "scanme.nmap.org",
    "10.0.0.1 10.0.0.2",
])
def test_valid_targets(targets):
    assert validate_targets(targets) == targets


@pytest.mark.parametrize("targets", [
    "",
    "-oN /etc/passwd",              # bare flag
    "127.0.0.1 -oN /tmp/out",       # smuggled flag via second token
    "127.0.0.1; rm -rf /",          # shell-ish junk
])
def test_invalid_targets(targets):
    with pytest.raises(ValueError):
        validate_targets(targets)


# --- ports ---

@pytest.mark.parametrize("ports", [None, "22", "22,80,443", "1-1024", "T:22,U:53"])
def test_valid_ports(ports):
    assert validate_ports(ports) == ports


@pytest.mark.parametrize("ports", ["-oN", "22 80", "abc", "22,"])
def test_invalid_ports(ports):
    with pytest.raises(ValueError):
        validate_ports(ports)


# --- arguments allowlist ---

@pytest.mark.parametrize("arguments", [
    None,
    "",
    "-sV",
    "-sS -Pn -T4",
    "--top-ports 100",
    "--top-ports=100",
    "--host-timeout 30m",
    "-sV --max-retries 2 -O",
])
def test_allowed_arguments(arguments):
    assert validate_arguments(arguments) == arguments


@pytest.mark.parametrize("arguments", [
    "-oN /tmp/out",             # file write
    "-oG /tmp/out",             # file write
    "-iL /etc/passwd",          # file read
    "--script vuln",            # NSE code execution
    "-sC",                      # default scripts
    "-A",                       # aggressive (enables scripts)
    "--datadir /tmp",
    "--top-ports abc",          # non-numeric value
    "--top-ports -5",           # value looks like a flag
    "--max-retries",            # missing value
])
def test_disallowed_arguments(arguments):
    with pytest.raises(ValueError):
        validate_arguments(arguments)


def test_unsafe_args_bypass(monkeypatch):
    from app import validation
    monkeypatch.setattr(validation.settings, "allow_unsafe_args", True)
    # Would normally be rejected; allowed when the escape hatch is on.
    assert validate_arguments("--script vuln -oN /tmp/out") == "--script vuln -oN /tmp/out"
