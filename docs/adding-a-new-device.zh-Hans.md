# 新增设备类型支持指南

> [English version / 英文版](./adding-a-new-device.md)

本指南是为 `midea-lan` 新增一款美的设备类型支持的完整流程。它遵循新增 `0xD9`
洗烘一体机时所用的完整步骤（见
[PR #175](https://github.com/wuwentao/midea-lan/pull/175)），你可以边阅读边把该
PR 当作具体范例参考。

本文同时面向人工贡献者与 AI 编码助手。每一步都会列出涉及的具体文件、需要继承的
基类，以及必须通过的检查项。

全文贯穿两个范例：

- **`0xD9`**（[PR #175](https://github.com/wuwentao/midea-lan/pull/175)）：扁平的
  TLV/多 bucket 设备，作为七个步骤的主线范例。
- **`0x9B`**（[PR #181](https://github.com/wuwentao/midea-lan/pull/181)）：子命令
  成帧的微蒸烤一体机，用到了解码器派生枚举、只写控制、带范围校验的数值参数，以及
  结构化的多步命令——参见[步骤 9](#9-第二个范例--0x9b-超出-d9-的模式)，它作为第二个
  范例，专门展示 D9 没有涉及的模式。

## 目录

1. [背景：三层协议结构](#1-背景三层协议结构)
2. [步骤 1 —— 获取设备 Lua 协议](#2-步骤-1--获取设备-lua-协议)
3. [步骤 2 —— 阅读 Lua：`dataToJson` 与 `jsonToData`](#3-步骤-2--阅读-luadatatojson-与-jsontodata)
4. [步骤 3 —— 编写 `devices/<type>/__init__.py`](#4-步骤-3--编写-devicestype__init__py)
5. [步骤 4 —— 编写 `devices/<type>/message.py`](#5-步骤-4--编写-devicestypemessagepy)
6. [步骤 5 —— 注册设备类型](#6-步骤-5--注册设备类型)
7. [步骤 6 —— 测试、Lint、覆盖率](#7-步骤-6--测试lint覆盖率)
8. [步骤 7 —— 提交 PR](#8-步骤-7--提交-pr)
9. [步骤 9 —— 第二个范例：0x9B 超出 D9 的模式](#9-第二个范例--0x9b-超出-d9-的模式)
10. [步骤 8 —— Home Assistant 侧（`midea_ac_lan`）](#10-步骤-8--home-assistant-侧midea_ac_lan)
11. [检查清单](#11-检查清单)

---

## 1. 背景：三层协议结构

协议分为三层。新增设备就是在通用层（1、2）之上编写按设备划分的第三层。前两层需要
阅读理解，但不要修改。

- **传输 / 组帧层** —— `device.py`、`packet_builder.py`、`security.py`、
  `crc8.py`。`MideaDevice` 是一个 `threading.Thread`，负责套接字、握手、
  token/key 鉴权，以及“加密 → 组帧 → CRC”流水线。你只需继承 `MideaDevice`，
  不要改动传输层。
- **通用消息层** —— `message.py`。基类 `MessageRequest`、`MessageResponse`、
  `MessageBody`、`NewProtocolMessageBody`，以及 `MessageType` 与 `ListTypes`
  枚举。每个设备消息都继承自它们。
- **按设备划分的包** —— `devices/<type>/`，每种设备一个目录，以设备类型字节的
  十六进制命名。这就是你要编写的部分。

### 包目录的命名规则

`midealan/devices/__init__.py` 中的 `device_selector()` 将设备类型字节映射为包名：

```python
if device_type < DeviceType.A0:  # 0xA0
    device_path = f".x{device_type:02x}"  # 如 0x13 -> "x13"、0x40 -> "x40"
else:
    device_path = f".{device_type:02x}"  # 如 0xD9 -> "d9"、0xAC -> "ac"
```

即：类型 `< 0xA0` 需加前缀 `x`（`x13`、`x40`、`x9c`）；类型 `>= 0xA0` 使用裸
十六进制（`ac`、`a1`、`d9`、`e2`）。目录名**必须**符合此规则，否则设备永远
不会被加载。

每个包恰好包含两个源文件：

- `__init__.py` —— 设备类（状态、查询、解析、控制）。
- `message.py` —— 该设备的请求/响应消息编解码。

---

## 2. 步骤 1 —— 获取设备 Lua 协议

美的云端为每个型号提供一个 Lua 文件，定义了每条查询、上报、控制消息的字节布局。
这是实现的唯一权威来源。

### 2.1 通过序列号（SN）下载 Lua

使用 `midealan` CLI 的 `download` 命令（完整参数见
[README](../README_hans.md#下载云端-lua-与插件文件)）。在源码检出环境中，把
`midealan` 替换为 `uv run python -m midealan.cli`：

```bash
uv run python -m midealan.cli download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password" \
  --device-sn "0000005112429652937220340014X2X3"
```

若序列号无法正确解析设备类型，用 `--device-type HEX` 显式指定（例如
`--device-type D9`）。也可用 `--host` 针对某个 LAN 设备下载，或同时省略
`--host` 与 `--device-sn` 处理整个云账号下的全部设备。Lua（以及在支持时的插件）
文件会写入当前工作目录 —— 建议使用一个全新的空目录集中保存。

### 2.2 将 Lua 提交到参考仓库

收集到的 Lua 文件统一发布在
[wuwentao/midea-lua](https://github.com/wuwentao/midea-lua) 供参考。下载到新设备
的 Lua 后，请贡献到该仓库（按类型组织，例如 `lua/0xD9/T_0000_D9_15.lua`），
方便后续工作直接查阅协议。并在你的 `midea-lan` PR 描述中引用该 Lua 路径。

> 提示：把新类型所依赖设备的 Lua 一并取回。D9 一体机复用了既有 `0xDB` 洗衣机与
> `0xDC` 干衣机 Lua 的语义，这三个文件共同定义了完整协议。

---

## 3. 步骤 2 —— 阅读 Lua：`dataToJson` 与 `jsonToData`

每个 Lua 文件暴露两个函数，恰好对应你要实现的两个方向：

| Lua 函数     | 方向                 | midea-lan 对应实现                                               |
| ------------ | -------------------- | ---------------------------------------------------------------- |
| `dataToJson` | 设备字节 → JSON 状态 | `message.py` 的**响应解析** + `__init__.py` 的 `process_message` |
| `jsonToData` | JSON 命令 → 设备字节 | `message.py` 的**设置消息** + `__init__.py` 的 `set_attribute`   |

### 3.1 `dataToJson` → 解析（读路径）

`dataToJson`（有时通过 `json2Table`/`decode` 之类的辅助函数）接收设备上报的原始
字节缓冲区，产出一张命名值表。阅读它以回答：

- **有效载荷从哪里开始？** 多数设备使用相对于 body 起点的固定字节偏移；也有设备
  （如 D9）使用 TLV（类型/长度/值）布局：body 第一个字节选择“bucket”，随后每个
  字段为 `<data_type><length><value...>`。
- **各字段的偏移/长度与字节序？** 注意多字节值及其字节序（D9 的值为小端序）。
- **原始值到标签的映射？** 例如 `runningStatus` 字节中 `2 = "start"`、
  `3 = "pause"`。它们将成为 `__init__.py` 中的 value-map 字典。

对 D9 而言，`dataToJson` 揭示了 TLV 组帧与各 bucket 的“data_type → 字段”映射，
它们成为
[`devices/d9/message.py`](../midealan/devices/d9/message.py) 中的
`DB_REPORT_MAP` / `DC_REPORT_MAP`。

### 3.2 `jsonToData` → 控制（写路径）

`jsonToData` 接收命令表（如 `{ power = true }`）并构造要发送的字节缓冲区。阅读它
以回答：

- **每个控制项由哪些命令字节编码？** D9 的共享控制记录类型为
  `power = 0x01`、`status/start = 0x02`、`program = 0x04`。
- **值如何编码？** 开关标志、枚举编码、按比例缩放的数值等。
- **是否存在每命令独立的 message type 或 body type？** 多数设置消息使用
  `MessageType.set` 搭配设备特定的 body type。

`jsonToData` 中每个独立命令对应 `message.py` 中的一个 `Message*` 设置类，并在
`set_attribute` 里接线。

---

## 4. 步骤 3 —— 编写 `devices/<type>/__init__.py`

该文件定义设备的状态模型及其四项职责：声明属性、构造查询、处理消息、设置属性。
以 [`devices/d9/__init__.py`](../midealan/devices/d9/__init__.py) 为模板。

### 4.1 用 `DeviceAttributes(StrEnum)` 声明属性

设备暴露的每一项状态都是 `StrEnum` 的一个成员。状态始终通过 `device.attributes`
字典（以这些名字为键）访问 —— 其他地方绝不按原始字节偏移访问。

```python
from enum import StrEnum


class DeviceAttributes(StrEnum):
    """Midea D9 device attributes."""

    db_power = "db_power"
    db_program = "db_program"
    db_running_status = "db_running_status"
    # ... 每个暴露字段一个成员
```

命名约定（属性**名**与其**值**都必须遵循 —— 它们会被下游直接消费，因此一致性
很重要）：

- 只使用小写 `snake_case`：ASCII 字母、数字与下划线（`_`）。不要有空格、
  camelCase、连字符或大写。枚举成员名与其值完全一致（`db_power = "db_power"`）。
- 名字保持稳定且描述状态本身，而非原始协议字段（如用 `remain_time`，而不是
  `t3` 或 `remainTime`）。
- 若设备有相互独立的子单元（如 D9 的洗衣机/干衣机），为每组加前缀
  （`db_*`、`dc_*`），使单一扁平命名空间保持无歧义。

为什么重要：Home Assistant 集成（`midea_ac_lan`）会把每个属性名**原样**用作
实体的 `translation_key`，而翻译键必须是小写 `snake_case`。在这里取好名字，HA
侧就能直接添加翻译键，无需任何重命名或映射层。参见
[步骤 8](#10-步骤-8--home-assistant-侧midea_ac_lan)。

### 4.2 设备类

继承 `MideaDevice`，传入 `DeviceType` 与初始属性字典，并把 value-map 查表声明为
`ClassVar` 字典。

```python
from typing import Any, ClassVar, Unpack
from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs


class MideaD9Device(MideaDevice):
    """Midea D9 device."""

    _db_running_status: ClassVar[dict[int, str]] = {
        0: "off",
        1: "standby",
        2: "start",
        3: "pause",
        4: "end",
        5: "fault",
        6: "delay",
    }
    # 原始上报值 -> 人类可读标签，在 process_message 时应用
    _value_maps: ClassVar[dict[str, dict[int, str]]] = {}

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002 （即使未用也需接收）
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea D9 device."""
        super().__init__(
            device_type=DeviceType.D9,
            **kwargs,
            attributes=dict.fromkeys(DeviceAttributes),
        )
```

`dict.fromkeys(DeviceAttributes)` 将每个属性初始化为 `None`，使得首条上报到达前
字典键已存在。

### 4.3 `build_query`

返回每次状态刷新时发送的查询消息列表。简单设备返回单条；当设备需要多条查询才能
覆盖完整状态时返回多条。D9 同时查询两个 bucket：

```python
def build_query(self) -> list[MessageQuery]:
    """同时查询两个 bucket，让洗衣机与干衣机状态一起刷新。"""
    return [
        MessageQuery(self._message_protocol_version, BUCKET_DB),
        MessageQuery(self._message_protocol_version, BUCKET_DC),
    ]
```

若设备需要在连接时执行一次性探测（例如某个能力查询，其回复会影响后续查询），
应改为重写 `build_init_query` —— 参见 `device.py` 中的 docstring。

### 4.4 `process_message`

把收到的帧解码为 `{属性名: 值}` 字典，应用 value-map 转换，写入
`self._attributes`，并返回本帧携带的属性（本代码库的惯例是返回该帧解码出的每个已
暴露键，而不是与上一次状态做差异比对）。

```python
def process_message(self, msg: bytes) -> dict[str, Any]:
    """Midea D9 device process message."""
    message = MessageD9Response(msg)
    new_status: dict[str, Any] = {}
    for name, value in message.attributes.items():
        if name not in self._attributes:
            continue  # 忽略我们不暴露的字段
        value_map = MideaD9Device._value_maps.get(name)
        self._attributes[name] = (
            value_map.get(value, value) if value_map is not None else value
        )
        new_status[name] = self._attributes[name]
    return new_status
```

响应对象暴露一个带类型的 `attributes: dict[str, int]`（见
[§5.3](#53-响应消息)）；`process_message` 从不直接接触原始字节。

### 4.5 `set_attribute`

把用户请求（`attr`、`value`）翻译成正确的设置消息，并通过 `build_send` 发送。
校验值类型并路由到对应消息。

```python
def set_attribute(self, attr: str, value: bool | float | str) -> None:
    """Midea D9 device set attribute."""
    bucket = BUCKET_DC if attr.startswith("dc_") else BUCKET_DB
    message = None
    if attr in (DeviceAttributes.db_power, DeviceAttributes.dc_power):
        if not isinstance(value, bool):
            raise ValueWrongType("[d9] Expected bool")
        message = MessagePower(self._message_protocol_version, bucket)
        message.power = value
    elif attr in (DeviceAttributes.db_program, DeviceAttributes.dc_program):
        program = self._resolve_program(bucket, value)
        if program is None:
            return  # 拒绝越界 / 非整数编码
        message = MessageProgram(self._message_protocol_version, bucket)
        message.program = program
    if message is not None:
        self.build_send(message)
```

值得照搬的防护措施：

- 当属性的值类型不正确时，抛出 `ValueWrongType`（来自 `midealan.exceptions`）。
- 把命名/枚举值映射为原始字节时，拒绝布尔、小数与越界值，避免被截断或回绕的
  编码发到设备（参见 D9 源码中的 `_resolve_program`）。

### 4.6 以 `MideaAppliance` 重新导出

`device_selector` 实例化的是 `module.MideaAppliance`，因此每个包都必须以别名结尾：

```python
class MideaAppliance(MideaD9Device):
    """Midea D9 appliance."""
```

---

## 5. 步骤 4 —— 编写 `devices/<type>/message.py`

该文件负责编码请求与解码响应。从 `midealan.message` 继承 `MessageRequest`
（请求）与 `MessageResponse` / `MessageBody`（响应）。

### 5.1 杜绝魔法数字

协议偏移、长度、命令字节、标志值都要写成命名的模块级常量。`ruff` 的 `PLR2004`
在 `tests/` 之外强制此规则。

```python
CONTROL_POWER = 0x01  # Lua: power（jsonToData 控制字节）
CONTROL_STATUS = 0x02  # Lua: status
CONTROL_PROGRAM = 0x04  # Lua: program
CONTROL_LENGTH_ONE = 0x01  # Lua: 单字节负载长度
VALUE_ON = 0x01  # Lua: on
VALUE_OFF = 0x00  # Lua: off
```

对固定偏移设备，则改为给每个字节偏移命名（参见 `devices/e2/message.py`，
例如 `HEATING_POWER_BYTE = 34`）。

请在每个常量和每条报文映射（report-map）条目旁用注释保留原始的 Lua 字段名。我们
对外暴露的属性名是为 Home Assistant 特意清理过的，因此与原始协议的关联会就此丢失。
把 Lua 名字写在旁边，能让下一位贡献者无需重新下载 Lua 就核对某字段，也能避免把
字段误映射到错误的偏移 —— 这是常见的 regression 来源。

```python
# TLV 的 data-type 字节 -> (属性名, 解码器)。注释记录原始 Lua 字段名，
# 便于对照协议重新核验映射关系。
DB_REPORT_MAP: dict[int, tuple[str, Callable[[bytes], int]]] = {
    0x01: ("db_power", _u8),  # lua: "power"
    0x02: ("db_running_status", _u8),  # lua: "runningStatus"
    0x04: ("db_program", _u8),  # lua: "program"
    0x0A: ("db_remain_time", _u16le),  # lua: "remainTime"（小端序）
}
```

### 5.2 一个基类请求 + 每条消息一个类

给设备一个小型基类，固定其 `DeviceType`，再按消息逐一子类化。每个子类设置
`message_type` 与 `body_type` 并实现 `_body`（body-type 字节之后的字节；框架会
在前面补上 body type，并在末尾补上头部/校验和）。

```python
class MessageD9Base(MessageRequest):
    def __init__(self, protocol_version, message_type, body_type):
        super().__init__(
            device_type=DeviceType.D9,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageD9Base):
    """查询一个 bucket；body 只有 bucket 字节。"""

    def __init__(self, protocol_version, bucket=BUCKET_DB):
        super().__init__(protocol_version, MessageType.query, bucket)

    @property
    def _body(self) -> bytearray:
        return bytearray([])  # 仅 body_type 字节即为查询


class MessagePower(MessageD9Base):
    """设置某个 bucket 的电源。"""

    def __init__(self, protocol_version, bucket=BUCKET_DB):
        super().__init__(protocol_version, MessageType.set, bucket)
        self.power = False

    @property
    def _body(self) -> bytearray:
        value = VALUE_ON if self.power else VALUE_OFF
        return bytearray([CONTROL_POWER, CONTROL_LENGTH_ONE, value])
```

在 `jsonToData` 中发现的每个命令都对应这样一个类（`MessagePower`、
`MessageStart`、`MessageProgram`……）。

### 5.3 响应消息

响应类把 body 解析成一个普通、带类型的 `attributes` 字典。把解析逻辑放进专门的
`MessageBody` 子类，并且只对本设备真正理解的 body type 执行解析。

```python
class D9GeneralMessageBody(MessageBody):
    def __init__(self, body: bytearray) -> None:
        super().__init__(body)
        bucket = body[0] if body else 0
        bucket_maps = {BUCKET_DB: DB_REPORT_MAP, BUCKET_DC: DC_REPORT_MAP}
        report_map = bucket_maps.get(bucket)
        self.attributes: dict[str, int] = {}
        if report_map is not None:  # 未知 bucket -> 保持为空
            self._parse_tlv(body, report_map)


class MessageD9Response(MessageResponse):
    def __init__(self, message: bytes) -> None:
        super().__init__(bytearray(message))
        self.attributes: dict[str, int] = {}
        if self.message_type in [
            MessageType.query,
            MessageType.set,
            MessageType.notify1,
        ] and self.body_type in [ListTypes.DB, ListTypes.DC, ListTypes.DA]:
            body = D9GeneralMessageBody(super().body)
            self.set_body(body)
            self.attributes = body.attributes
        self.set_attr()
```

三点务必照搬：

- **优先使用带类型的 `attributes: dict[str, int]`**，而非动态 `setattr`。严格的
  `mypy` 配置（同样会检查 `tests/`）会标记它看不到的属性；用普通字典能让类型
  保持清晰，也让 `process_message` 更简单。
- **只解析已识别的 body type。** D9 只接受 `DB`/`DC`，并防止用错误的字段映射去
  解析无关 bucket（这是 PR #175 上一条真实的评审意见：`DA` body 不得用 `DB`
  映射解码）。
- **为每个解析出的字段标注其 Lua 来源。** 把解析值赋给属性时，用简短注释记录
  Lua 字段名以及任何编码细节（缩放系数、字节序、位掩码）。这就是某个偏移或映射
  条目“为何如此”的记录；缺了它，后续修改可能悄悄错位某个字段，若样例载荷不完整，
  测试也未必能捕获，从而引入 regression。

对固定偏移设备，body 子类改为读取命名偏移
（`self.power = (body[POWER_BYTE] & 0x01) > 0  # lua: "power"`）—— 参见
`devices/e2/message.py`。

---

## 6. 步骤 5 —— 注册设备类型

两处注册使设备可被发现：

1. **`midealan/const.py` 的 `DeviceType`**：加入类型字节，保持十六进制顺序。

   ```python
   class DeviceType(IntEnum):
       ...
       D9 = 0xD9
       DA = 0xDA
   ```

2. **`midealan/message.py` 的 `ListTypes`**：该枚举已列出 `0x00`–0xFF 的每个
   字节，因此 body type 通常已存在。仅当你需要一个缺失的符号名时才新增条目。
   请引用你使用的 body type（如 `ListTypes.DB`），而非裸整数。

无需改动 `device_selector` —— 它依据目录名动态解析包（见 §1）。只要确保目录名对
类型 `< 0xA0` 遵循 `x` 前缀规则即可。

---

## 7. 步骤 6 —— 测试、Lint、覆盖率

测试镜像源码树，位于 `tests/` 下，以 `_test.py` 结尾
（如 `tests/devices/d9/message_d9_test.py`、
`tests/devices/d9/device_d9_test.py`）。样例二进制载荷放在 `tests/responses/`。
`tests/*` 的 ruff/mypy 规则较宽松（允许 assert、访问私有成员、魔法数字）。

至少覆盖：

- 每条设置消息序列化为期望的确切字节（电源开/关、启动、程序……）。
- 响应解析器把代表性的上报缓冲区解码为正确的属性值，包括 value-map 转换。
- 呼应评审意见的边界情形：未知/其他 body type 解析为空、空 body 解析为空、
  非法设置值被拒绝。

推送前在本地跑通完整关卡：

```bash
# 全部测试
uv run python -m pytest ./tests/

# 仅本设备
uv run python -m pytest tests/devices/d9/ -v

# 覆盖率（新代码目标为 100%）
uv run python -m pytest --cov=midealan --cov-report xml ./tests/

# 一次性执行 lint / format / 类型检查 / pylint
uv run prek run --all-files
```

CI 会在多 OS/Python 矩阵（Python 3.12–3.14）上运行完整的 `prek` 套件，任一失败
都会阻止合并。争取让新包达到 100% 行 + 分支覆盖率 —— D9 以 41 个测试达到了 100%。

---

## 8. 步骤 7 —— 提交 PR

遵循仓库约定（见 [CONTRIBUTING](../.github/CONTRIBUTING.zh.md)）：

- **分支**：绝不直接提交到 `main`（有 prek 钩子拦截）。使用特性分支，如
  `feat/d9-washer-dryer-combo`。
- **Conventional Commits**：`feat(d9): add combined washer/dryer device support`。
  commitlint/commitizen 与 CI 会校验格式。
- **PR 描述**：概述该设备，链接 `wuwentao/midea-lua` 中的 Lua 文件，并说明
  覆盖率。如实陈述你验证了什么。
- **CodeRabbit**：该 AI 评审会跳过草稿 PR。要让草稿获得评审，评论
  `@coderabbitai review`。逐条处理所有意见，并在对应线程中回复，说明修复方式与
  覆盖它的测试。

可参照的范例 PR：

- [PR #175 —— `feat(d9)`](https://github.com/wuwentao/midea-lan/pull/175)：
  TLV/多 bucket 设备（本指南的贯穿示例）。
- [PR #181 —— `feat(x9b)`](https://github.com/wuwentao/midea-lan/pull/181)：
  子命令成帧的烤箱，用到解码器派生枚举、只写控制、带范围校验的数值参数，以及
  结构化的多步命令——参见[步骤 9](#9-第二个范例--0x9b-超出-d9-的模式)。
- `feat(x9c)`（提交 `feb1c64`）：一个 `< 0xA0` 的类型，使用 `x` 前缀目录。
- `feat(c1): add support for Midea C1 device`（PR #117）：一个直白的固定偏移设备。

---

## 9. 第二个范例 —— 0x9B 超出 D9 的模式

上面的 D9 范例是一个扁平的 TLV 设备，其控制都是“一命令一属性”。许多设备比它复杂。
`0x9B` 微蒸烤一体机（[PR #181](https://github.com/wuwentao/midea-lan/pull/181)）同样
按这七个步骤构建，但它用到了一些 D9 流程没有展示的模式。当你的设备符合下述场景时，
就可以采用它们。

对照阅读成品文件：
[`devices/x9b/__init__.py`](../midealan/devices/x9b/__init__.py) 与
[`devices/x9b/message.py`](../midealan/devices/x9b/message.py)。

### 9.1 从解码器派生属性枚举（避免漂移）

D9 手写它的 `DeviceAttributes(StrEnum)`。当设备上报几十个字段时，让手写枚举与解析器
保持同步很容易出错。0x9B（与 0x9C 一样）改为在 `message.py` 里用一个元组列出解码器
可能产生的全部属性，再在 `__init__.py` 中据此构建枚举：

```python
# message.py —— 属性名的唯一真实来源。
ALL_ATTRIBUTES: tuple[str, ...] = (
    "execute",
    "cloudmenuid",
    "work_mode",
    "fire_power",
    "temperature",
    # ... 解码器会产生的每个状态字段 ...
    # 只写控制（见 §9.2），然后是系统时间字段。
    "power",
    "door",
    "camera",
    "screen_luminance",
    "volume",
    "sys_time_src",
    "sys_second",  # ...
)
```

```python
# __init__.py —— 枚举永远不会与解码器产出漂移。
from enum import StrEnum
from .message import ALL_ATTRIBUTES

DeviceAttributes = StrEnum(  # type: ignore[misc]
    "DeviceAttributes",
    {name: name for name in ALL_ATTRIBUTES},
)

# ... 并用同一个元组初始化属性字典：
super().__init__(
    device_type=DeviceType.X9B,
    **kwargs,
    attributes=dict.fromkeys(ALL_ATTRIBUTES),
)
```

当字段列表很长或可能增长时采用此法。对于小而稳定的设备，手写枚举（D9 风格）就够了。

### 9.2 只写（合成）属性

有些控制在状态上报里没有对应的 bit——设备接受命令但从不回报该值（0x9B 的
`power`、`door`、`camera`、`screen_luminance`、`volume`）。仍把它们分组并加注释地列入
`ALL_ATTRIBUTES`，这样 `set_attribute` 能寻址到它们，Home Assistant 侧也能为每个映射
一个控制实体：

```python
# 只写控制（设备不上报，仅为通过 ``set_attribute`` 寻址所有控制的调用方
# （如 Home Assistant）暴露）。
(
    "power",
    "door",
    "camera",
    "screen_luminance",
    "volume",
)
```

当某个逻辑上重要的值其实可以从上报内容推导时，应在解码器里合成它，而不是留空。0x9B
没有电源字节，于是从运行状态推导一个：

```python
status = WORK_STATUS_MAP.get(self._body[31], VALUE_FF)
attrs["work_status"] = status
# 设备不上报专门的电源字节，因此按 HA 电源开关的预期推导开关状态：
# 除省电待机（或未知字节）以外的任何状态都视为已开机。
attrs["power"] = status not in ("save_power", VALUE_FF)
```

> HA 侧的正确性提示：HA 渲染为 switch、binary_sensor 或 lock 的标志，必须解码为真正的
> `bool`，而不是字符串 `"on"`/`"off"`。HA 把任何非空字符串都当作真值，因此字符串标志
> 会一直卡在“开”。0x9B 正是出于这个原因用 `bool(...)` 解码这些标志（在构建配套的
> HA PR 时所做的修复）。根据消费该值的实体来确定 Python 类型。

### 9.3 按属性分组路由 `set_attribute`，并做范围校验

D9 用一连串 `if attr in (…)` 做路由。0x9B 控制更多，于是在 `message.py` 里把它们
分组为元组（`STATE_STR_ATTRIBUTES`、`STATE_INT_ATTRIBUTES`、`PARAM_U16_ATTRIBUTES`、
`PARAM_BYTE_ATTRIBUTES`），并按成员归属分派。关键是，数值控制在上线前会做**范围
校验**——抛出 `ValueOutOfRange`（而不仅是 `ValueWrongType`），这样被回绕或截断的字节
绝不会到达设备：

```python
from midealan.exceptions import ValueOutOfRange, ValueWrongType


@staticmethod
def _coerce_int(attr: str, value: bool | float | str, low: int, high: int) -> int:
    # 先拒绝 bool 与非数字；在 Python 中 bool 是 int 的子类。
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueWrongType(f"[x9b] {attr} expects a number")
    # 拒绝小数而不是静默截断（42.7 -> 42），否则会向设备发送与调用方
    # 请求不同的控制值。
    if isinstance(value, float) and not value.is_integer():
        raise ValueWrongType(f"[x9b] {attr} must be a whole number")
    coerced = int(value)
    if not low <= coerced <= high:
        raise ValueOutOfRange(f"[x9b] {attr} must be in [{low}, {high}]")
    return coerced
```

u16 温度按 `0..65535` 校验，单字节音量按 `0..255` 校验。两处边界都是命名常量
（`U16_MIN/U16_MAX`、`BYTE_MIN/BYTE_MAX`），绝不用字面量——`ruff` 的 `PLR2004` 在
`tests/` 之外强制这一点。

### 9.4 子命令成帧（body 第一个字节选择命令组）

D9 把它的 bucket 选择器放在通用的 `body_type` 里。0x9B 则把**子命令字节作为 body 的
第一个字节**（`0x01` 状态/开始烹饪、`0x02` 状态控制、`0x03` 实时参数 TLV、`0x04`
系统时间），并且**不**需要框架的 `body_type` 前缀。重写 `body`，原样返回 `_body`：

```python
class MessageX9BBase(MessageRequest):
    @property
    def body(self) -> bytearray:
        """0x9B 协议把子命令放在 body 的第一个字节本身，
        因此这里不前置通用的 ``body_type`` 前缀。"""
        return self._body
```

每个消息类随后用正确的子命令常量开启它的 `_body`。如果你的 Lua 显示命令选择器位于
负载内部而非类型字节中，就复制这个模式。

### 9.5 结构化的多字段命令

并非每个命令都是单属性。0x9B 的“开始烹饪”接收一整份菜谱：云菜单 id、步骤数，以及
一个或多个 16 字节的步骤块（模式、定时、火力、分段温度、探针、重量/份量、结束行为）。
它被建模为一个简单的普通类加一个组装这些块的消息：

```python
class CookingStep:
    """一个烹饪步骤；encode() 返回其 16 字节块。"""

    def encode(self) -> bytearray:
        flags = 0
        if self.pre_heat:
            flags |= COOK_FLAG_PREHEAT
        if self.turntable:
            flags |= COOK_FLAG_TURNTABLE
        # ... 打包模式、定时、火力、分段温度、探针、份量 ...
        return bytearray([...])


class MessageSetCooking(MessageX9BBase):
    """单步或多步的开始烹饪控制。"""

    # body = [SUBCMD_COOKING, menu_hi, menu_mid, menu_lo, step_count_nibble,
    #         *step.encode() for each step, 0x00]
```

通过一个带类型的构造器（而非 `set_attribute`）暴露结构化命令，并重新导出该构造器类，
以便调用方构造菜谱。简单的单值控制照常留在 `set_attribute` 上。

### 9.6 一个解码器服务两个固件版本

0x9B 发行了 V1（单字节温度）与 V2（双字节温度加额外字段）两种固件。解码器不做分支，
而是把 **V2 当作规范化的超集**：对 V1 也上报的字段，两者编码一致（V1 把值放在 V2
双字节对的低字节里），因此一个固定偏移解码器同时服务两者。如果你的设备有固件变体，
先确认其中之一是否为另一个的超集，再决定是否要写两套代码路径。

用长度检查守护每一次固定偏移读取，让过短/截断的 body 解码为空而不是抛异常（两个守护
都是命名常量，长度守护本身来自 PR #181 上一条 CodeRabbit 意见）：

```python
STATUS_MIN_LEN = 36  # 最后一次固定偏移状态字节读取的是 body[35]
SYSTIME_MIN_LEN = 10  # 系统时间 body 读取 body[1]..body[9]


def _decode(self) -> None:
    if len(self._body) < STATUS_MIN_LEN:
        return
    # ... 固定偏移读取现在是安全的 ...
```

### 9.7 set 回显携带完整状态

0x9B 对 `set` 的回复是完整的状态记录（而非裸 ack），因此响应解析器用与查询相同的状态
解码器来解码 `set` 消息：

```python
if self.message_type == MessageType.set:
    # set 回显报文携带完整的状态记录。
    self.attributes = X9BStatusBody(body).attributes
```

如果你的设备在写入时回显状态，就解码它——UI 便能立即反映变化，无需等待下一次轮询。

---

## 10. 步骤 8 —— Home Assistant 侧（`midea_ac_lan`）

`midea-lan` 是协议库；Home Assistant 集成
[`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) 消费它。库支持该设备
后，再在 HA 中暴露它（通常是一个依赖库版本发布的独立 PR）：

- **`custom_components/midea_ac_lan/midea_devices.py`**：导入该设备的
  `DeviceAttributes`，并注册一个 `0x<TYPE>:` 条目，包含 `name` 与 `entities`
  映射（每个属性 → `Platform.SENSOR` / `SWITCH` / …，并带 `translation_key`、
  `name`、`icon`，以及可选的 `unit`/`device_class`/`state_class`）。
- **翻译**：把每个实体的 `translation_key` 加入
  `custom_components/midea_ac_lan/translations/` 下的所有语言文件，至少包含
  `en.json` 与 `zh-Hans.json`。
- **文档**：新增 `doc/<TYPE>.md` 与 `doc/<TYPE>_hans.md`，列出实体与
  `set_attribute` 服务。
- **README**：在 `README.md` 与 `README_hans.md` 中新增该设备行。

D9 对应的集成参见
[`midea_ac_lan` 的 PR #1086](https://github.com/wuwentao/midea_ac_lan/pull/1086)。

---

## 11. 检查清单

- [ ] 通过 SN 下载了设备 Lua，并贡献到 `wuwentao/midea-lua`。
- [ ] 阅读了 `dataToJson`（解析）与 `jsonToData`（控制）以梳理协议。
- [ ] 创建了 `devices/<type>/`，目录名正确（`< 0xA0` 加 `x` 前缀）。
- [ ] `__init__.py`：`DeviceAttributes`、设备类、`build_query`、
      `process_message`、`set_attribute`，以及 `MideaAppliance` 别名。
- [ ] `message.py`：命名常量、基类请求、每命令一个类、只处理已识别 body type 的
      响应解析。
- [ ] 在 `const.py` 的 `DeviceType` 中注册了类型（如有需要也在 `ListTypes`）。
- [ ] 测试镜像源码树；新包 100% 覆盖率。
- [ ] `uv run prek run --all-files` 通过。
- [ ] 在特性分支上提 PR，标题为 Conventional Commit，链接 Lua，处理完 CodeRabbit
      意见。
- [ ] （若在 HA 中暴露）更新 `midea_ac_lan` 的设备条目、翻译、文档与 README。
</content>
