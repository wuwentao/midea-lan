# Adding a New Device Type

> [中文版 / Chinese version](./adding-a-new-device.zh-Hans.md)

This guide is the end-to-end recipe for adding support for a new Midea appliance
type to `midea-lan`. It follows the exact flow used to add the `0xD9`
washer/dryer combo in [PR #175](https://github.com/wuwentao/midea-lan/pull/175),
so you can use that PR as a concrete worked example while reading.

It is written for both human contributors and AI coding agents. Every step lists
the concrete files, the base classes to extend, and the checks that must pass.

## Contents

1. [Background: the three protocol layers](#1-background-the-three-protocol-layers)
2. [Step 1 — Obtain the device Lua protocol](#2-step-1--obtain-the-device-lua-protocol)
3. [Step 2 — Read the Lua: `dataToJson` and `jsonToData`](#3-step-2--read-the-lua-datatojson-and-jsontodata)
4. [Step 3 — Build `devices/<type>/__init__.py`](#4-step-3--build-devicestype__init__py)
5. [Step 4 — Build `devices/<type>/message.py`](#5-step-4--build-devicestypemessagepy)
6. [Step 5 — Register the device type](#6-step-5--register-the-device-type)
7. [Step 6 — Tests, lint, coverage](#7-step-6--tests-lint-coverage)
8. [Step 7 — Submit the PR](#8-step-7--submit-the-pr)
9. [Step 8 — Home Assistant side (`midea_ac_lan`)](#9-step-8--home-assistant-side-midea_ac_lan)
10. [Checklist](#10-checklist)

---

## 1. Background: the three protocol layers

The protocol is split into three layers. Adding a device means writing the
per-device layer (3) on top of the generic layers (1) and (2), which you should
read but not modify.

- **Transport / framing** — `device.py`, `packet_builder.py`, `security.py`,
  `crc8.py`. `MideaDevice` is a `threading.Thread` that owns the socket,
  handshake, token/key auth, and the encrypt → frame → CRC pipeline. You extend
  `MideaDevice`; you do not touch the transport.
- **Generic messages** — `message.py`. Base classes `MessageRequest`,
  `MessageResponse`, `MessageBody`, `NewProtocolMessageBody`, plus the
  `MessageType` and `ListTypes` enums. Every device message subclasses these.
- **Per-device package** — `devices/<type>/`, one folder per appliance type
  named by the device-type byte in hex. This is what you write.

### Naming rule for the package folder

`device_selector()` in `midealan/devices/__init__.py` maps the device-type byte
to a package name:

```python
if device_type < DeviceType.A0:  # 0xA0
    device_path = f".x{device_type:02x}"  # e.g. 0x13 -> "x13", 0x40 -> "x40"
else:
    device_path = f".{device_type:02x}"  # e.g. 0xD9 -> "d9", 0xAC -> "ac"
```

So types `< 0xA0` are prefixed with `x` (`x13`, `x40`, `x9c`); types `>= 0xA0`
use the bare hex (`ac`, `a1`, `d9`, `e2`). The folder **must** match this rule or
the device will never load.

Each package has exactly two source files:

- `__init__.py` — the device class (state, query, parse, control).
- `message.py` — that device's request/response message encoders/decoders.

---

## 2. Step 1 — Obtain the device Lua protocol

The Midea cloud ships a per-model Lua file that defines the byte layout of every
query, report, and control message. This is the source of truth for the
implementation.

### 2.1 Download the Lua by serial number

Use the `midealan` CLI `download` command (see the
[README](../README.md#downloading-cloud-lua-and-plugin-files) for full options).
From a checkout, replace `midealan` with `uv run python -m midealan.cli`:

```bash
uv run python -m midealan.cli download \
  --cloud-name "SmartHome" --username "user@example.com" --password "password" \
  --device-sn "0000005112429652937220340014X2X3"
```

If the serial number does not resolve the device type correctly, pass it
explicitly with `--device-type HEX` (for example `--device-type D9`). You can
also download for a LAN device with `--host`, or for the whole account by
omitting both `--host` and `--device-sn`. The Lua (and, where supported, the
plugin) files are written to the current working directory — use a fresh empty
directory to keep them together.

### 2.2 Submit the Lua to the reference repo

Collected Lua files are published for reference in
[wuwentao/midea-lua](https://github.com/wuwentao/midea-lua). After you download a
new device's Lua, contribute it there (organised by type, e.g.
`lua/0xD9/T_0000_D9_15.lua`) so future work has the protocol on hand. Reference
the Lua path in your `midea-lan` PR description.

> Tip: also grab the Lua for any devices your new type builds on. The D9 combo
> reused the semantics of the existing `0xDB` washer and `0xDC` dryer Lua, so
> those three files together defined the full protocol.

---

## 3. Step 2 — Read the Lua: `dataToJson` and `jsonToData`

Each Lua file exposes two functions that map directly onto the two directions you
implement:

| Lua function | Direction                   | midea-lan counterpart                                                     |
| ------------ | --------------------------- | ------------------------------------------------------------------------- |
| `dataToJson` | device bytes → JSON state   | **response parsing** in `message.py` + `process_message` in `__init__.py` |
| `jsonToData` | JSON command → device bytes | **set messages** in `message.py` + `set_attribute` in `__init__.py`       |

### 3.1 `dataToJson` → parsing (read path)

`dataToJson` (sometimes via a helper like `json2Table`/`decode`) takes the raw
byte buffer the appliance reports and produces a table of named values. Read it
to answer:

- **Where does the payload start?** Most devices use fixed byte offsets from the
  body start. Some (like D9) use a TLV — type/length/value — layout where the
  first body byte selects a "bucket" and each field is
  `<data_type><length><value...>`.
- **What is each field's offset/length and byte order?** Note multi-byte values
  and endianness (D9 values are little-endian).
- **What raw values map to which labels?** e.g. a `runningStatus` byte where
  `2 = "start"`, `3 = "pause"`. These become the value-map dicts in
  `__init__.py`.

For D9, `dataToJson` revealed the TLV framing and the per-bucket data-type →
field maps, which became `DB_REPORT_MAP` / `DC_REPORT_MAP` in
[`devices/d9/message.py`](../midealan/devices/d9/message.py).

### 3.2 `jsonToData` → control (write path)

`jsonToData` takes a command table (e.g. `{ power = true }`) and builds the byte
buffer to send. Read it to answer:

- **Which command bytes encode each control?** For D9 the shared control record
  types are `power = 0x01`, `status/start = 0x02`, `program = 0x04`.
- **What is the value encoding?** on/off flags, enumerated codes, scaled numbers.
- **Is there a per-command message type or body type?** Most set messages use
  `MessageType.set` with a device-specific body type.

Each distinct command in `jsonToData` becomes one `Message*` set class in
`message.py`, wired up in `set_attribute`.

---

## 4. Step 3 — Build `devices/<type>/__init__.py`

This file defines the device's state model and its four responsibilities:
declare attributes, build queries, process messages, and set attributes. Use
[`devices/d9/__init__.py`](../midealan/devices/d9/__init__.py) as the template.

### 4.1 Declare attributes with a `DeviceAttributes(StrEnum)`

Every piece of state the device exposes is a member of a `StrEnum`. State is
always accessed through the `device.attributes` dict keyed by these names — never
by raw byte offset elsewhere.

```python
from enum import StrEnum


class DeviceAttributes(StrEnum):
    """Midea D9 device attributes."""

    db_power = "db_power"
    db_program = "db_program"
    db_running_status = "db_running_status"
    # ... one member per exposed field
```

Naming conventions (both the attribute **name** and its **value** must follow
these — they are consumed downstream, so consistency matters):

- Use lowercase `snake_case` only: ASCII letters, digits, and underscores (`_`).
  No spaces, camelCase, hyphens, or uppercase. The enum member name and its value
  are identical (`db_power = "db_power"`).
- Keep names stable and descriptive of the state, not the raw protocol field
  (e.g. `remain_time`, not `t3` or `remainTime`).
- If the device has independent sub-units (like D9's washer/dryer), prefix each
  group (`db_*`, `dc_*`) so a single flat namespace stays unambiguous.

Why this matters: the Home Assistant integration (`midea_ac_lan`) uses each
attribute name **verbatim** as the entity's `translation_key`, and translation
keys must be lowercase `snake_case`. Picking a clean name here means the HA side
can add the translation key directly with no renaming or mapping layer. See
[Step 8](#9-step-8--home-assistant-side-midea_ac_lan).

### 4.2 The device class

Extend `MideaDevice`, pass the `DeviceType` and the initial attribute dict, and
declare any value-map lookups as `ClassVar` dicts.

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
    # raw report value -> human label, applied during process_message
    _value_maps: ClassVar[dict[str, dict[int, str]]] = {}

    def __init__(
        self,
        *,
        customize: str,  # noqa: ARG002  (accept even if unused)
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea D9 device."""
        super().__init__(
            device_type=DeviceType.D9,
            **kwargs,
            attributes=dict.fromkeys(DeviceAttributes),
        )
```

`dict.fromkeys(DeviceAttributes)` seeds every attribute to `None` so the dict
keys exist before the first report arrives.

### 4.3 `build_query`

Return the list of query messages sent on every status refresh. Return one
message for a simple device; return several when the device needs multiple
queries to cover its full state. D9 queries both buckets:

```python
def build_query(self) -> list[MessageQuery]:
    """Query both buckets so washer and dryer state refresh together."""
    return [
        MessageQuery(self._message_protocol_version, BUCKET_DB),
        MessageQuery(self._message_protocol_version, BUCKET_DC),
    ]
```

If the device needs one-time probes at connect time (e.g. a capability query
whose reply shapes later queries), override `build_init_query` instead — see the
docstring in `device.py`.

### 4.4 `process_message`

Decode an incoming frame into a `{attr_name: value}` dict, apply any value-map
translation, store into `self._attributes`, and return only the changed keys.

```python
def process_message(self, msg: bytes) -> dict[str, Any]:
    """Midea D9 device process message."""
    message = MessageD9Response(msg)
    new_status: dict[str, Any] = {}
    for name, value in message.attributes.items():
        if name not in self._attributes:
            continue  # ignore fields we don't expose
        value_map = MideaD9Device._value_maps.get(name)
        self._attributes[name] = (
            value_map.get(value, value) if value_map is not None else value
        )
        new_status[name] = self._attributes[name]
    return new_status
```

The response object exposes a typed `attributes: dict[str, int]` (see
[§5.3](#53-response-message)); `process_message` never reaches into raw bytes.

### 4.5 `set_attribute`

Translate a user request (`attr`, `value`) into the correct set message and send
it via `build_send`. Validate the value type and route to the right message.

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
            return  # reject out-of-range / non-integer codes
        message = MessageProgram(self._message_protocol_version, bucket)
        message.program = program
    if message is not None:
        self.build_send(message)
```

Guard-rails worth copying:

- Raise `ValueWrongType` (from `midealan.exceptions`) when the value type is
  wrong for the attribute.
- When mapping a named/enumerated value to a raw byte, reject bools, fractional
  numbers, and out-of-range values so a truncated or wrapped code never reaches
  the appliance (see `_resolve_program` in the D9 source).

### 4.6 Re-export as `MideaAppliance`

`device_selector` instantiates `module.MideaAppliance`, so every package must end
with the alias:

```python
class MideaAppliance(MideaD9Device):
    """Midea D9 appliance."""
```

---

## 5. Step 4 — Build `devices/<type>/message.py`

This file encodes requests and decodes responses. Extend `MessageRequest`
(requests) and `MessageResponse` / `MessageBody` (responses) from
`midealan.message`.

### 5.1 No magic numbers

Protocol offsets, lengths, command bytes, and flag values are named
module-level constants. `ruff`'s `PLR2004` enforces this outside `tests/`.

```python
CONTROL_POWER = 0x01
CONTROL_STATUS = 0x02
CONTROL_PROGRAM = 0x04
CONTROL_LENGTH_ONE = 0x01
VALUE_ON = 0x01
VALUE_OFF = 0x00
```

For a fixed-offset device, name each byte offset instead (see
`devices/e2/message.py`, e.g. `HEATING_POWER_BYTE = 34`).

Carry the original Lua field name in a comment next to each constant and each
report-map entry. The attribute names we expose are deliberately cleaned up for
Home Assistant, so the link back to the raw protocol is otherwise lost. Keeping
the Lua name inline lets the next contributor re-check a field against the Lua
without re-downloading it, and prevents accidentally re-mapping a field to the
wrong offset — a common source of regressions.

```python
# TLV data-type byte -> (attribute name, decoder).  The comment records the
# original Lua field name so the mapping can be re-verified against the protocol.
DB_REPORT_MAP: dict[int, tuple[str, Callable[[bytes], int]]] = {
    0x01: ("db_power", _u8),  # lua: "power"
    0x02: ("db_running_status", _u8),  # lua: "runningStatus"
    0x04: ("db_program", _u8),  # lua: "program"
    0x0A: ("db_remain_time", _u16le),  # lua: "remainTime" (little-endian)
}
```

### 5.2 A base request + one class per message

Give the device a small base that pins its `DeviceType`, then subclass it per
message. Each subclass sets `message_type` and `body_type` and implements
`_body` (the bytes after the body-type byte; the framework prepends the body
type and appends header/checksum).

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
    """Query one bucket; body is just the bucket byte."""

    def __init__(self, protocol_version, bucket=BUCKET_DB):
        super().__init__(protocol_version, MessageType.query, bucket)

    @property
    def _body(self) -> bytearray:
        return bytearray([])  # body_type byte alone is the query


class MessagePower(MessageD9Base):
    """Set power for one bucket."""

    def __init__(self, protocol_version, bucket=BUCKET_DB):
        super().__init__(protocol_version, MessageType.set, bucket)
        self.power = False

    @property
    def _body(self) -> bytearray:
        value = VALUE_ON if self.power else VALUE_OFF
        return bytearray([CONTROL_POWER, CONTROL_LENGTH_ONE, value])
```

Create one such class for each command you found in `jsonToData` (`MessagePower`,
`MessageStart`, `MessageProgram`, …).

### 5.3 Response message

The response class parses the body into a plain, typed `attributes` dict. Keep
the parsing in a dedicated `MessageBody` subclass and only run it for the body
types this device actually understands.

```python
class D9GeneralMessageBody(MessageBody):
    def __init__(self, body: bytearray) -> None:
        super().__init__(body)
        bucket = body[0] if body else 0
        bucket_maps = {BUCKET_DB: DB_REPORT_MAP, BUCKET_DC: DC_REPORT_MAP}
        report_map = bucket_maps.get(bucket)
        self.attributes: dict[str, int] = {}
        if report_map is not None:  # unknown bucket -> leave empty
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

Three things to copy:

- **Prefer a typed `attributes: dict[str, int]`** over dynamic `setattr`. The
  strict `mypy` config (which also checks `tests/`) flags attributes it cannot
  see; a plain dict keeps typing honest and `process_message` simple.
- **Only parse recognised body types.** D9 accepts `DB`/`DC` and guards against
  parsing an unrelated bucket with the wrong field map (a real review finding on
  PR #175: a `DA` body must not be decoded with the `DB` map).
- **Comment each parsed field with its Lua origin.** When you assign a parsed
  value to an attribute, note the Lua field name and any encoding quirk (scale
  factor, byte order, bit mask) in a short comment. This is the record of _why_
  an offset or map entry is what it is; without it, a future edit can silently
  shift a field and introduce a regression that tests may not catch if the
  sample payloads are incomplete.

For a fixed-offset device, the body subclass instead reads named offsets
(`self.power = (body[POWER_BYTE] & 0x01) > 0  # lua: "power"`) — see
`devices/e2/message.py`.

---

## 6. Step 5 — Register the device type

Two registrations make the device discoverable:

1. **`midealan/const.py` — `DeviceType`**: add the type byte, kept in hex order.

   ```python
   class DeviceType(IntEnum):
       ...
       D9 = 0xD9
       DA = 0xDA
   ```

2. **`midealan/message.py` — `ListTypes`**: this enum already lists every byte
   `0x00`–0xFF, so a body type is usually present. Add an entry only if you need
   a symbolic name that is missing. Reference the body types you use
   (`ListTypes.DB`, etc.) rather than raw ints.

No change to `device_selector` is needed — it resolves the package
dynamically from the folder name (§1). Just make sure the folder name follows the
`x`-prefix rule for types `< 0xA0`.

---

## 7. Step 6 — Tests, lint, coverage

Tests mirror the source tree under `tests/`, suffixed `_test.py`
(e.g. `tests/devices/d9/message_d9_test.py`,
`tests/devices/d9/device_d9_test.py`). Sample binary payloads live in
`tests/responses/`. `tests/*` has relaxed ruff/mypy rules (asserts, private
access, magic numbers).

Cover at least:

- Each set message serialises to the exact expected bytes (power on/off, start,
  program, …).
- The response parser decodes representative report buffers into the right
  attribute values, including value-map translation.
- Edge cases that mirror review findings: unknown/other body types parse to
  nothing, empty bodies parse to nothing, invalid set values are rejected.

Run the full local gate before pushing:

```bash
# all tests
uv run python -m pytest ./tests/

# just your device
uv run python -m pytest tests/devices/d9/ -v

# coverage (CI enforces 100% on new code)
uv run python -m pytest --cov=midealan --cov-report xml ./tests/

# lint / format / type-check / pylint in one shot
uv run prek run --all-files
```

CI runs the full `prek` suite across the OS/Python matrix (Python 3.12–3.14) and
blocks merge on any failure. Aim for 100% line + branch coverage on the new
package — D9 landed at 100% with 41 tests.

---

## 8. Step 7 — Submit the PR

Follow the repository conventions (see
[CONTRIBUTING](../.github/CONTRIBUTING.md)):

- **Branch**: never commit to `main` (a prek hook blocks it). Use a feature
  branch, e.g. `feat/d9-washer-dryer-combo`.
- **Conventional Commits**: `feat(d9): add combined washer/dryer device support`.
  commitlint/commitizen and CI validate the format.
- **PR description**: summarise the device, link the Lua file(s) in
  `wuwentao/midea-lua`, and note coverage. State plainly what was verified.
- **CodeRabbit**: the AI reviewer skips draft PRs. To get a review on a draft,
  comment `@coderabbitai review`. Address every finding and reply in-thread
  documenting the fix and the covering test.

Reference worked examples to model your PR on:

- [PR #175 — `feat(d9)`](https://github.com/wuwentao/midea-lan/pull/175):
  a TLV/multi-bucket device (this guide's running example).
- `feat(x9c)` (commit `feb1c64`): a `< 0xA0` type using the `x`-prefix folder.
- `feat(c1): add support for Midea C1 device` (PR #117): a straightforward
  fixed-offset device.

---

## 9. Step 8 — Home Assistant side (`midea_ac_lan`)

`midea-lan` is the protocol library; the Home Assistant integration
[`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) consumes it. After the
library supports the device, expose it in HA (typically a separate PR that
depends on the library release):

- **`custom_components/midea_ac_lan/midea_devices.py`**: import the device's
  `DeviceAttributes` and register a `0x<TYPE>:` entry with a `name` and an
  `entities` map (each attribute → `Platform.SENSOR` / `SWITCH` / … with
  `translation_key`, `name`, `icon`, and optional `unit`/`device_class`/
  `state_class`).
- **Translations**: add each entity's `translation_key` to every file in
  `custom_components/midea_ac_lan/translations/` (all languages), at minimum
  `en.json` and `zh-Hans.json`.
- **Docs**: add `doc/<TYPE>.md` and `doc/<TYPE>_hans.md` listing the entities and
  the `set_attribute` service.
- **README**: add the device row to `README.md` and `README_hans.md`.

See [PR #1086 on `midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan/pull/1086)
for the matching D9 integration.

---

## 10. Checklist

- [ ] Downloaded the device Lua by SN and contributed it to `wuwentao/midea-lua`.
- [ ] Read `dataToJson` (parse) and `jsonToData` (control) to map the protocol.
- [ ] Created `devices/<type>/` with the correct folder name (`x`-prefix if
      `< 0xA0`).
- [ ] `__init__.py`: `DeviceAttributes`, device class, `build_query`,
      `process_message`, `set_attribute`, and the `MideaAppliance` alias.
- [ ] `message.py`: named constants, base request, one class per command, a
      response body parser that only handles recognised body types.
- [ ] Registered the type in `const.py` `DeviceType` (and `ListTypes` if needed).
- [ ] Tests mirror the source tree; 100% coverage on the new package.
- [ ] `uv run prek run --all-files` passes.
- [ ] PR on a feature branch, Conventional Commit title, Lua linked, CodeRabbit
      findings resolved.
- [ ] (If exposing in HA) `midea_ac_lan` device entry, translations, docs, and
    README updated.
</content>
