# midea-lan python lib

[![Python build](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml/badge.svg)](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml)
[![Stable](https://img.shields.io/github/v/release/wuwentao/midea-lan)](https://github.com/wuwentao/midea-lan/releases/latest)
[![codecov](https://codecov.io/gh/wuwentao/midea-lan/graph/badge.svg?token=MSM6KLLTYK)](https://codecov.io/gh/wuwentao/midea-lan)

> [中文版 / Chinese README](./README_hans.md)

## Menu

- [Getting started](#getting-started)
- [Development](#development)
- [Contributing guide](#contributing-guide)
- [Sponsor this project](#sponsor-this-project)

Control your Midea M-Smart appliances via local area network.

This library is part of https://github.com/wuwentao/midea_ac_lan code.
⭐If this component is helpful for you, please star it, it encourages me a lot.

## Getting started

### Finding your device

```python3
from midealan.discover import discover

# Without knowing the ip address
discover()
# If you know the ip address
discover(ip_address="203.0.113.11")
# The device type is in hexadecimal as in midealan/devices/TYPE
type_code = hex(list(discover().values())[0]["type"])[2:]
```

### Getting data from device

```python3
from midealan.discover import discover
from midealan.devices import device_selector

token = "..."
key = "..."

# Get the first device
d = list(discover().values())[0]
# Select the device
ac = device_selector(
    name="AC",
    device_id=d["device_id"],
    device_type=d["type"],
    ip_address=d["ip_address"],
    port=d["port"],
    token=token,
    key=key,
    device_protocol=d["protocol"],
    model=d["model"],
    subtype=0,
    customize="",
)

# Connect and authenticate
ac.connect()

# Getting the attributes
print(ac.attributes)
# Setting the temperature
ac.set_target_temperature(23.0, None)
# Setting the swing
ac.set_swing(False, False)
```

### Command line tool

The package installs a `midealan` console command. From a clone of this repository, create
the development environment, install the package in editable mode, and activate the virtual
environment first:

```bash
# Linux / macOS / WSL2
git clone https://github.com/wuwentao/midea-lan.git
cd midea-lan
./scripts/setup.sh
uv pip install -e .
source .venv/bin/activate

midealan --help
```

On Windows PowerShell, run `scripts\setup.ps1`, then `uv pip install -e .` and
`.\.venv\Scripts\Activate.ps1` before using `midealan --help`. The console command is
installed inside `.venv`, so use `uv run` when the virtual environment is not activated:

```bash
uv run python -m midealan.cli -h
```

Available commands are `discover`, `info`, `decode`, `save`, `download`, and `setattr`. Run
`midealan <command> --help` (or the `uv run` equivalent) for command-specific options. When
working from a checkout, replace `midealan` in the examples below with
`uv run python -m midealan.cli`.

#### Cloud credentials

`discover` (for V3 devices), `info`, and `download` sign in to a Midea cloud account to
retrieve each device's token/key or cloud-side details. They share these options:

- `--username` / `-u`, `--password` / `-p`, and `--cloud-name` / `-cn`.
- `--debug` / `-d` turns on debug logging (available on every command).

Supported `--cloud-name` values are `美的美居`, `SmartHome`, `Midea Air`, `NetHome Plus`,
and `Ariston Clima`.

When complete user credentials are not supplied, the CLI uses its preset account with
`SmartHome` as the default cloud. Pass or save all three credential fields to select another
cloud.

`save` writes the credentials to a `midea-lan.json` config file so later commands can omit
them. Without `--user` it writes `midea-lan.json` in the current directory; with `--user` it
writes to the per-user config folder. Any command auto-loads this file and fills in only the
username, password, and cloud name you did not pass on the command line.

```bash
# store credentials in the current directory (./midea-lan.json)
midealan save --cloud-name "美的美居" --username "user@example.com" --password "secret"

# store them in the per-user config folder instead
midealan save --user --cloud-name "美的美居" --username "user@example.com" --password "secret"
```

#### Discovering devices on the LAN

`discover` scans the local network, authenticates every supported device, and prints the
attributes it reads back. Unsupported devices are listed with the reason they were skipped.
V3 devices need cloud credentials so the command can fetch their token/key.

```bash
# scan the whole LAN
midealan discover --cloud-name "美的美居" --username "user@example.com" --password "secret"

# query a single device
midealan discover --host 192.0.2.121 \
  --cloud-name "美的美居" --username "user@example.com" --password "secret"
```

`--get_sn` reads only the device serial number instead of the full attribute set. On 2024+
TLS devices the LAN serial is encrypted and cannot be read this way; use the cloud serial
shown by `info` instead.

#### Listing cloud account appliances

`info` signs in to the cloud account and lists every appliance grouped by the home (group)
it belongs to, so an account with several homes shows each home's devices under its own
header instead of merged into one list. For each device it prints the name, device type,
model, sn8, Wi-Fi module version, and online state. The Wi-Fi version is only returned by
the `美的美居` cloud; other clouds leave it blank.

```bash
midealan info --cloud-name "美的美居" --username "user@example.com" --password "secret"
```

```text
Home 63535541 (Home A): 2 device(s)
  Device 1: name Living Room AC, type 0xAC, model KFR-72L, sn8 22270043, wifi_version 059009012205, online True
  Device 2: name Washer, type 0xDB, model MD100, sn8 38127874, wifi_version None, online False
Home 107400725 (Home B): 1 device(s)
  Device 3: name Kitchen Hood, type 0xEA, model CXW-200, sn8 12345678, wifi_version None, online True
Found 3 device(s) across 2 home(s) in the cloud account.
```

#### Decoding a captured message

`decode` parses a raw hex frame offline; no network connection or cloud account is needed.
The device type is taken from the third byte of the frame.

```bash
midealan decode aa20ac00000000000003418100ff03ff000200000000000000000000000003cd9d
```

#### Setting a device attribute

`setattr` discovers the device at `host`, sets one `attribute` to `value`, waits for the
change to apply, then prints the refreshed status. `--attr-type` controls how `value` is
parsed: `int` (the default), `bool`, or `str`. V3 devices need cloud credentials for the
discovery step.

```bash
midealan setattr 192.0.2.121 power true --attr-type bool \
  --cloud-name "美的美居" --username "user@example.com" --password "secret"
```

The `download` command has its own section below.

### Downloading cloud Lua and plugin files

The `download` command signs in to a supported Midea cloud account, downloads the Lua
protocol file for each selected appliance, then tries to download its plugin. Files are
written to the current working directory. Use a separate empty directory if you want to
keep the downloads together.

Collected Lua files are published for reference in
[wuwentao/midea-lua](https://github.com/wuwentao/midea-lua); contributions with additional
device Lua files are welcome there. Pull requests should link the exact Lua source when
a device protocol applies, or explain why no protocol source applies. If the Lua is not
present yet, follow the `midea-lua` README to download it and submit it there first, then
link that pull request from the `midea-lan` pull request.

```text
midealan download [--debug] --username USERNAME --password PASSWORD \
  --cloud-name CLOUD [--host HOST | --device-sn SERIAL [--device-type HEX]]
```

Download for a device discovered at a LAN address:

```bash
midealan download \
  --cloud-name "美的美居" --username "user@example.com" --password "password" \
  --host 192.0.2.121
```

Download for one serial number from the cloud account:

```bash
midealan download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password" \
  --device-sn "0000005112429652937220340014X2X3"
```

Pass an explicit hexadecimal device type when the serial number does not identify the
device type correctly:

```bash
midealan download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password" \
  --device-sn "0000005112429652937220340014X2X3" --device-type AC
```

Omit both `--host` and `--device-sn` to process every appliance in the cloud account:

```bash
midealan download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password"
```

`--host` takes precedence when it is supplied with `--device-sn`; LAN discovery provides
the serial number, type, and model. For a serial-number download, the device type is
resolved in this order: `--device-type`, a matching appliance in the cloud account, then
the legacy type byte in the serial number. A malformed or unsupported serial-number
fallback uses type `0`, so pass `--device-type` when known.

Each appliance is handled independently during account-wide downloads. A Lua or plugin
failure is logged and later appliances continue to be processed. `美的美居` and
`SmartHome` support Lua and plugin downloads. The legacy `Midea Air`, `NetHome Plus`, and
`Ariston Clima` backend supports Lua downloads but not plugin downloads; the command logs
a warning after a successful Lua download. Add `--debug` when diagnosing a failed request,
and verify the files actually created in the working directory.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for its development environment.
After [installing uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
git clone https://github.com/wuwentao/midea-lan.git
cd midea-lan
./scripts/setup.sh          # Linux / macOS / WSL2  (Windows: scripts\setup.ps1)
```

This creates a `.venv`, installs all dependencies, and sets up the prek hooks.
Run tools with `uv run`, e.g. `uv run python -m pytest ./tests/`. See the contributing
guide for the full workflow and per-OS uv install instructions.

## Contributing Guide

[CONTRIBUTING](.github/CONTRIBUTING.md)
[中文版CONTRIBUTING](.github/CONTRIBUTING.zh.md)

Pull requests use the repository template to record protocol sources, related issues,
tests, 100% patch coverage, and CodeRabbit review resolution. The integration manifest
is the sole source of its `midea-lan` runtime requirement; CI and local setup install
from `manifest.json`, while its `pyproject.toml` and `uv.lock` contain development/test
dependencies only. Before this `midea-lan` lib PR merges, the corresponding
`midea_ac_lan` integration PR may point the `midea-lan` requirement in its manifest at
the contributor fork/branch for CI and end-to-end testing. After the lib PR merges,
switch only the integration manifest to `wuwentao/midea-lan@main` unless it already
points there. The integration PR may merge only when its manifest uses upstream `main`
or a released version containing all library changes it depends on; it must not
retain a contributor fork/branch. This avoids waiting
for a library release. Maintainers periodically publish `midea-lan` and `midea_ac_lan`
based on merged PRs: they generate the changelog, update the integration manifest to
the released library version containing the merged changes, and publish the integration release.

### Adding a new device

Want to add support for a new Midea appliance type? The end-to-end recipe —
downloading the device Lua protocol, reading `dataToJson`/`jsonToData`, building
`__init__.py` and `message.py`, registering the type, testing, and opening a PR
— is documented, using the `0xD9` washer/dryer combo
([PR #175](https://github.com/wuwentao/midea-lan/pull/175)) as the running example
and the `0x9B` microwave/steam/convection oven
([PR #181](https://github.com/wuwentao/midea-lan/pull/181)) as a second example
for richer devices:

- [Adding a New Device Type](docs/adding-a-new-device.md)
- [新增设备类型支持指南（中文）](docs/adding-a-new-device.zh-Hans.md)

## Sponsor this project

If this project helps you, consider sponsoring its ongoing development, maintenance, and community support.

<p>
  <a href="https://buymeacoffee.com/wuwentao"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="40"></a>
  <a href="https://www.paypal.me/wuwentao2000"><img src="https://www.paypalobjects.com/webstatic/mktg/Logo/pp-logo-200px.png" alt="PayPal" height="40"></a>
</p>
