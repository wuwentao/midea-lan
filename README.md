# midea-lan python lib

[![Python build](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml/badge.svg)](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml)
[![Stable](https://img.shields.io/github/v/release/wuwentao/midea-lan)](https://github.com/wuwentao/midea-lan/releases/latest)
[![codecov](https://codecov.io/gh/wuwentao/midea-lan/graph/badge.svg?token=MSM6KLLTYK)](https://codecov.io/gh/wuwentao/midea-lan)

> [中文版 / Chinese README](./README_hans.md)

Control your Midea M-Smart appliances via local area network.

This library is part of https://github.com/georgezhao2010/midea_ac_lan code. It was separated to segregate responsibilities.

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
type_code = hex(list(discover().values())[0]['type'])[2:]
```

### Getting data from device

```python3
from midealan.discover import discover
from midealan.devices import device_selector

token = '...'
key = '...'

# Get the first device
d = list(discover().values())[0]
# Select the device
ac = device_selector(
  name="AC",
  device_id=d['device_id'],
  device_type=d['type'],
  ip_address=d['ip_address'],
  port=d['port'],
  token=token,
  key=key,
  device_protocol=d['protocol'],
  model=d['model'],
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

Available commands are `discover`, `decode`, `save`, `download`, and `setattr`. Run
`midealan <command> --help` (or the `uv run` equivalent) for command-specific options.

### Downloading cloud Lua and plugin files

The `download` command signs in to a supported Midea cloud account, downloads the Lua
protocol file for each selected appliance, then tries to download its plugin. Files are
written to the current working directory. Use a separate empty directory if you want to
keep the downloads together.

Collected Lua files are published for reference in
[wuwentao/midea-lua](https://github.com/wuwentao/midea-lua); contributions with additional
device Lua files are welcome there.

```text
midealan download [--debug] --username USERNAME --password PASSWORD \
  --cloud-name CLOUD [--host HOST | --device-sn SERIAL [--device-type HEX]]
```

When working from a checkout, replace `midealan` in the examples below with
`uv run python -m midealan.cli`.

Supported `--cloud-name` values are `美的美居`, `SmartHome`, `Midea Air`, `NetHome Plus`,
and `Ariston Clima`.

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
