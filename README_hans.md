# midea-lan Python 库

[![Python build](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml/badge.svg)](https://github.com/wuwentao/midea-lan/actions/workflows/python-build.yml)
[![Stable](https://img.shields.io/github/v/release/wuwentao/midea-lan)](https://github.com/wuwentao/midea-lan/releases/latest)
[![codecov](https://codecov.io/gh/wuwentao/midea-lan/graph/badge.svg?token=MSM6KLLTYK)](https://codecov.io/gh/wuwentao/midea-lan)

> [English README](./README.md)

## 导航

- [快速开始](#快速开始)
- [开发环境](#开发环境)
- [贡献指南](#贡献指南)
- [赞助本项目](#赞助本项目)

通过局域网控制你的美的 M-Smart 智能家电。

本lib库是 https://github.com/wuwentao/midea_ac_lan 项目的一部分。

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
type_code = hex(list(discover().values())[0]["type"])[2:]
```

### 从设备获取数据

```python3
from midealan.discover import discover
from midealan.devices import device_selector

token = "..."
key = "..."

# 获取第一个设备
d = list(discover().values())[0]
# 选择设备
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

本包安装后会提供 `midealan` 控制台命令。从本仓库克隆代码时，先创建开发环境、以 editable
模式安装本包，并激活虚拟环境：

```bash
# Linux / macOS / WSL2
git clone https://github.com/wuwentao/midea-lan.git
cd midea-lan
./scripts/setup.sh
uv pip install -e .
source .venv/bin/activate

midealan --help
```

在 Windows PowerShell 中，先运行 `scripts\setup.ps1`，再依次运行 `uv pip install -e .` 和
`.\.venv\Scripts\Activate.ps1`，之后即可使用 `midealan --help`。控制台命令安装在 `.venv`
中；未激活虚拟环境时，请使用 `uv run`：

```bash
uv run python -m midealan.cli -h
```

可用子命令为 `discover`、`info`、`decode`、`save`、`download` 和 `setattr`。使用
`midealan <子命令> --help`（或对应的 `uv run` 命令）查看各子命令参数。在本仓库开发环境中，
请将以下示例中的 `midealan` 替换为 `uv run python -m midealan.cli`。

#### 云账号凭据

`discover`（针对 V3 设备）、`info` 和 `download` 需要登录美的云账号，以获取设备的
token/key 或云端信息。它们共用以下参数：

- `--username` / `-u`、`--password` / `-p` 和 `--cloud-name` / `-cn`。
- `--debug` / `-d` 开启调试日志（所有子命令均可用）。

`--cloud-name` 支持的值为：`美的美居`、`SmartHome`、`Midea Air`、`NetHome Plus` 和
`Ariston Clima`。

`save` 会把凭据写入 `midea-lan.json` 配置文件，之后的命令便可省略这些参数。不加 `--user`
时写入当前目录的 `midea-lan.json`；加 `--user` 时写入用户配置目录。任何命令都会自动读取该
文件，并仅补全你在命令行中未提供的用户名、密码和云名称。

```bash
# 将凭据保存到当前目录（./midea-lan.json）
midealan save --cloud-name "美的美居" --username "user@example.com" --password "secret"

# 改为保存到用户配置目录
midealan save --user --cloud-name "美的美居" --username "user@example.com" --password "secret"
```

#### 在局域网发现设备

`discover` 会扫描局域网，对每台受支持的设备完成鉴权，并打印读取到的属性。无法识别的设备会
连同跳过原因一并列出。V3 设备需要云账号凭据，命令才能获取其 token/key。

```bash
# 扫描整个局域网
midealan discover --cloud-name "美的美居" --username "user@example.com" --password "secret"

# 仅查询单台设备
midealan discover --host 192.0.2.121 \
  --cloud-name "美的美居" --username "user@example.com" --password "secret"
```

`--get_sn` 只读取设备序列号，而不读取完整属性。2024 年后的 TLS 设备在局域网上的序列号是加密
的，无法通过这种方式读取；请改用 `info` 显示的云端序列号。

#### 列出云账号下的设备

`info` 会登录云账号，并按设备所属的家庭（分组）分别列出每台设备。因此当账号下有多个家庭时，
各家庭的设备会显示在各自的标题下，而不是混在一个列表里。对每台设备会打印名称、设备类型、
型号、sn8、Wi-Fi 模组版本和在线状态。Wi-Fi 版本仅 `美的美居` 云会返回，其他云留空。

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

#### 解码抓取到的报文

`decode` 可离线解析原始十六进制报文，无需联网或云账号。设备类型取自报文的第三个字节。

```bash
midealan decode aa20ac00000000000003418100ff03ff000200000000000000000000000003cd9d
```

#### 设置设备属性

`setattr` 会发现 `host` 处的设备，将某个 `attribute` 设置为 `value`，等待设置生效后打印刷新
后的状态。`--attr-type` 控制 `value` 的解析方式：`int`（默认）、`bool` 或 `str`。V3 设备的
发现步骤需要云账号凭据。

```bash
midealan setattr 192.0.2.121 power true --attr-type bool \
  --cloud-name "美的美居" --username "user@example.com" --password "secret"
```

`download` 子命令的详细说明见下一节。

### 下载云端 Lua 与插件文件

`download` 会登录支持的美的云账号，为每台选中的设备下载 Lua 协议文件，然后尝试下载插件。
文件会写入当前工作目录；建议在专门的空目录中执行命令，以便集中保存下载结果。

已收集的 Lua 文件会发布在 [wuwentao/midea-lua](https://github.com/wuwentao/midea-lua)
作为参考，也欢迎在该仓库提交 PR 补充更多设备的 Lua 文件。PR 涉及设备协议时应链接
准确的 Lua 来源，不适用时则说明原因；如果尚未收录，请按照 `midea-lua` README 下载并
先向该仓库提交 PR，然后在 `midea-lan` PR 中链接该 PR。

```text
midealan download [--debug] --username USERNAME --password PASSWORD \
  --cloud-name CLOUD [--host HOST | --device-sn SERIAL [--device-type HEX]]
```

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

提交 PR 时请按仓库模板填写协议来源、关联 Issue、测试、100% 增量覆盖率及 CodeRabbit
评审处理情况。会影响 Home Assistant 集成的改动应同时提交并链接 `midea_ac_lan` PR。
当前 `midea-lan` lib PR 尚未合并时，对应的 `midea_ac_lan` 集成 PR 可以把 `manifest.json` 中的 `midea-lan` 指向你的 fork/分支，以便运行 CI
和端到端测试。集成仓库的 CI 与本地开发环境直接从 `manifest.json` 安装运行时依赖；其
`pyproject.toml` 与 `uv.lock` 只包含开发和测试依赖，不包含 `midea-lan`。库 PR 合并后，只需
将 manifest 改为 `wuwentao/midea-lan@main`（若已指向则无需修改）。集成 PR 只能在 manifest
指向上游 `main` 或包含集成 PR 所依赖全部库改动的正式发布版本时才能合并，因此无需等待库发布。lib PR 合并后不会立即发布库版本，但集成 PR 无需等待：将 manifest 切换到上游 `main` 后即可继续验证。维护者会根据已合并的 PR 定期发布集成版本：生成 changelog，将 manifest 中的 `midea-lan` 更新为包含所需库改动的正式发布版本，并发布 `midea_ac_lan` release。

### 新增设备支持

想为一款新的美的设备类型添加支持？从下载设备 Lua 协议、阅读
`dataToJson`/`jsonToData`、编写 `__init__.py` 与 `message.py`、注册设备类型、
测试，到提交 PR 的完整流程都有文档说明，并以 `0xD9` 洗烘一体机
（[PR #175](https://github.com/wuwentao/midea-lan/pull/175)）作为贯穿示例，另以
`0x9B` 微蒸烤一体机（[PR #181](https://github.com/wuwentao/midea-lan/pull/181)）
作为面向更复杂设备的第二个范例：

- [新增设备类型支持指南（中文）](docs/adding-a-new-device.zh-Hans.md)
- [Adding a New Device Type（English）](docs/adding-a-new-device.md)

## 赞助本项目

如果这个项目对你有帮助，欢迎赞助项目的持续开发、日常维护和社区支持。

<p>
  <a href="https://buymeacoffee.com/wuwentao"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="40"></a>
  <a href="https://www.paypal.me/wuwentao2000"><img src="https://www.paypalobjects.com/webstatic/mktg/Logo/pp-logo-200px.png" alt="PayPal" height="40"></a>
</p>
