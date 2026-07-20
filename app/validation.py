from __future__ import annotations

import re
import shlex

from app.config import settings

# --- targets / ports ---

# IPs, CIDRs, octet ranges (192.168.1.1-127), hostnames, and the "*" wildcard.
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-/*]+$")
# e.g. "22,80,443", "1-1024", "T:22,U:53" (comma-separated ports/ranges, each
# with an optional T:/U:/S: protocol prefix; no empty or trailing segments).
_PORTS_RE = re.compile(r"^([TUS]:)?\d+(-\d+)?(,([TUS]:)?\d+(-\d+)?)*$")


def validate_targets(targets: str) -> str:
    tokens = shlex.split(targets)
    if not tokens:
        raise ValueError("targets must not be empty")
    for tok in tokens:
        # A leading "-" would be parsed by nmap as a flag, not a host.
        if tok.startswith("-") or not _HOST_RE.match(tok):
            raise ValueError(f"invalid target: {tok!r}")
    return targets


def validate_ports(ports: str | None) -> str | None:
    if ports is not None and not _PORTS_RE.match(ports):
        raise ValueError(f"invalid ports specification: {ports!r}")
    return ports


# --- arguments allowlist ---

# Standalone flags with no side effects beyond scanning. Notably excluded:
# -sC / -A / --script* (NSE code execution), -oN/-oG/-oA/-oS (file write),
# -iL/-iR/--excludefile (file read), --datadir/--stylesheet/--resume, and -p
# (use the dedicated `ports` field instead).
_ALLOWED_FLAGS = {
    # scan techniques
    "-sS", "-sT", "-sU", "-sA", "-sW", "-sM", "-sN", "-sF", "-sX", "-sn", "-sV",
    # host discovery / dns / target selection
    "-Pn", "-n", "-R", "-6", "-r", "-F",
    # detection
    "-O",
    # output verbosity / diagnostics
    "-v", "-vv", "-vvv", "-d", "-dd",
    # timing templates
    "-T0", "-T1", "-T2", "-T3", "-T4", "-T5",
    # informational
    "--open", "--reason", "--traceroute", "--packet-trace",
}

# Flags that consume one numeric/duration value (e.g. "--top-ports 100",
# "--host-timeout 30m"). The value is validated by _VALUE_RE.
_ALLOWED_VALUE_FLAGS = {
    "--top-ports", "--max-retries", "--host-timeout", "--scan-delay",
    "--max-scan-delay", "--min-rate", "--max-rate", "--min-parallelism",
    "--max-parallelism", "--min-hostgroup", "--max-hostgroup",
    "--max-rtt-timeout", "--min-rtt-timeout", "--initial-rtt-timeout", "--mtu",
}

# Plain integers, or nmap durations like "500ms", "30s", "15m", "2h".
_VALUE_RE = re.compile(r"^\d+(?:ms|s|m|h)?$")


def validate_arguments(arguments: str | None) -> str | None:
    """Reject any nmap flag not on the allowlist.

    Bypassed entirely when SCANPOD_ALLOW_UNSAFE_ARGS is true, for trusted
    deployments that need the full nmap surface.
    """
    if settings.allow_unsafe_args:
        return arguments

    tokens = shlex.split(arguments or "")
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # Support "--flag=value" as well as "--flag value".
        flag, sep, inline_value = tok.partition("=")

        if flag in _ALLOWED_FLAGS and not sep:
            i += 1
            continue

        if flag in _ALLOWED_VALUE_FLAGS:
            if sep:
                value = inline_value
                i += 1
            else:
                if i + 1 >= len(tokens):
                    raise ValueError(f"argument {flag!r} requires a value")
                value = tokens[i + 1]
                i += 2
            if not _VALUE_RE.match(value):
                raise ValueError(f"invalid value for {flag!r}: {value!r}")
            continue

        raise ValueError(f"disallowed argument: {tok!r}")

    return arguments
