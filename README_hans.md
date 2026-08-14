# midea-lan Python 库

[![Python build](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml/badge.svg)](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml)
[![Stable](https://img.shields.io/github/v/release/wuwentao/midea-lan)](https://github.com/wuwentao/midea-lan/releases/latest)
[![codecov](https://codecov.io/gh/wuwentao/midea-lan/graph/badge.svg?token=MSM6KLLTYK)](https://codecov.io/gh/wuwentao/midea-lan)

> [English README](./README.md)

通过局域网控制你的美的 M-Smart 智能家电。

本库源自 https://github.com/georgezhao2010/midea_ac_lan 项目，为了职责分离而拆分独立。

⭐ 如果这个组件对你有帮助，请点个 star，这对我是很大的鼓励。

## 快速开始

### 发现设备

```python3
from midealan.discover import discover
# 未知 IP 地址时
discover()
# 已知 IP 地址时
discover(ip_address="203.0.113.11")
# 设备类型为十六进制，对应 midealan/devices/TYPE
type_code = hex(list(discover().values())[0]['type'])[2:]
```

### 从设备获取数据

```python3
from midealan.discover import discover
from midealan.devices import device_selector

token = '...'
key = '...'

# 获取第一个设备
d = list(discover().values())[0]
# 选择设备
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

# 连接并认证
ac.connect()

# 获取属性
print(ac.attributes)
# 设置温度
ac.set_target_temperature(23.0, None)
# 设置摆风
ac.set_swing(False, False)
```

### 命令行工具

已安装包时使用 `midealan` 命令；从本仓库开发环境运行时使用 `uv run`：

```bash
# 已安装的软件包
midealan --help

# 本仓库开发环境
uv run python -m midealan.cli -h
```

可用子命令为 `discover`、`decode`、`save`、`download` 和 `setattr`。使用
`midealan <子命令> --help`（或对应的 `uv run` 命令）查看各子命令参数。

### 下载云端 Lua 与插件文件

`download` 会登录支持的美的云账号，为每台选中的设备下载 Lua 协议文件，然后尝试下载插件。
文件会写入当前工作目录；建议在专门的空目录中执行命令，以便集中保存下载结果。

已收集的 Lua 文件会发布在 [wuwentao/midea-lua](https://github.com/wuwentao/midea-lua)
作为参考，也欢迎在该仓库提交 PR 补充更多设备的 Lua 文件。

```text
midealan download [--debug] --username USERNAME --password PASSWORD \
  --cloud-name CLOUD [--host HOST | --device-sn SERIAL [--device-type HEX]]
```

在本仓库开发环境中，请将以下示例中的 `midealan` 替换为
`uv run python -m midealan.cli`。

`--cloud-name` 支持的值为：`美的美居`、`SmartHome`、`Midea Air`、`NetHome Plus` 和
`Ariston Clima`。

按局域网地址发现并下载一台设备：

```bash
midealan download \
  --cloud-name "美的美居" --username "user@example.com" --password "password" \
  --host 192.0.2.121
```

按云账号内的设备序列号下载：

```bash
midealan download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password" \
  --device-sn "0000005112429652937220340014X2X3"
```

当序列号无法正确推导设备类型时，可以显式传入十六进制设备类型：

```bash
midealan download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password" \
  --device-sn "0000005112429652937220340014X2X3" --device-type AC
```

省略 `--host` 和 `--device-sn` 时，会处理云账号内的全部设备：

```bash
midealan download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password"
```

同时传入 `--host` 和 `--device-sn` 时，`--host` 优先；程序会通过局域网发现获取序列号、
设备类型和型号。按序列号下载时，设备类型按以下顺序确定：`--device-type`、云账号中匹配
设备的信息、序列号中的旧格式类型字节。序列号格式错误或不支持旧格式回退时，类型会使用
`0`，因此已知类型时应传入 `--device-type`。

批量下载时，每台设备独立处理；某台设备的 Lua 或插件下载失败只会记录日志，后续设备仍会
继续处理。`美的美居` 与 `SmartHome` 支持 Lua 和插件下载。旧版 `Midea Air`、
`NetHome Plus` 和 `Ariston Clima` 后端支持 Lua 下载，但不支持插件下载；Lua 下载成功后，
命令会记录相应警告。排查请求失败时可添加 `--debug`，并检查当前工作目录中实际生成的文件。

## 开发环境

本项目使用 [uv](https://docs.astral.sh/uv/) 管理开发环境。
在[安装 uv](https://docs.astral.sh/uv/getting-started/installation/) 之后：

```bash
git clone https://github.com/wuwentao/midea-lan.git
cd midea-lan
./scripts/setup.sh          # Linux / macOS / WSL2 （Windows 使用 scripts\setup.ps1）
```

该脚本会创建 `.venv`、安装所有依赖并配置 prek 钩子。
使用 `uv run` 运行工具，例如 `uv run python -m pytest ./tests/`。
完整流程与各操作系统的 uv 安装说明请参见贡献指南。

## 贡献指南

[英文版 CONTRIBUTING](.github/CONTRIBUTING.md)
[中文版 CONTRIBUTING](.github/CONTRIBUTING.zh.md)
