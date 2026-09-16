# 个人修复分支：0xAC 备用查询族探测（issue #658）

- 分支：`personal/ac-probe-fallback-fix`
- 基于：`wuwentao/midea-lan` 的 `main`（`ae97f4f`），三个提交都可以单独 cherry-pick
- 上游 PR：见分支对应的 Pull Request（同一套提交，分支名 `fix/probe-fallback-family`）

这个分支是我自用/待上游合并的版本，用来修
[wuwentao/midea_ac_lan#658](https://github.com/wuwentao/midea_ac_lan/issues/658)：
中央空调 min（型号 223J6397 / subtype 1，SN 210006734918980）在 Home Assistant 里
一直不可用，只能手动重载集成才能短暂恢复。

## 现象与实测根因

云端可以控制、局域网可连通、TCP 连接和 V3 认证都成功，但插件最终报
`NoSupportedProtocol`，实体不可用。实测（HA 日志 + 设备回帧）：

1. 设备会正常回答 appliance query（`MessageQueryAppliance`），报文字协议版本正常返回。
2. 它对主查询族（B5 `CapabilitiesQuery` / `0x41` 状态查询）**全部超时**。
3. 它对 BB 子协议族（`SubProtocolQuery10/11/30`）**立刻正常回复**。
4. 于是 `refresh_status(check_protocol=True)` 把这 8 条主查询全部写进
   `_unsupported_protocol`，`error_count == len(real_cmds)` → `raise NoSupportedProtocol`
   → `close_socket()` → 重连后又用同一族探测 → 永远失败；同时退避时间会涨到 600 秒，
   所以看起来就是"集成卡死，必须手动重载"。
5. 手工发只读帧 `aa0800ffff1063dd`（`SubProtocolQuery10`）后设备立刻回 BB 帧：
   室内 29.5 °C、湿度 53%、室外 25.5 °C，`_used_subprotocol` 置位，三个实体恢复。

## 改动点（3 个提交）

| 提交 | 文件 | 说明 |
| --- | --- | --- |
| `fix: retry a timed-out protocol probe once before blacklisting` | `midealan/device.py` | 协议探测时，单次超时不再直接把命令拉黑：`QUERY_PROBE_RETRIES = 2`，重发前清空 `_buffer`（避免半帧粘到重试回包导致解帧失败）；重发的 **写** 超时属于链路故障，向上抛给连接恢复而不是拉黑。 |
| `fix: cap the reconnect backoff at one minute` | `midealan/device.py` | 重连退避上限从 600 秒降到 `MAX_RECONNECT_SLEEP = 60`：设备恢复后最多 1 分钟自动接回，不用手动重载。 |
| `fix(ac): probe an alternative query family before giving up` | `midealan/device.py`、`midealan/devices/ac/__init__.py` | 新增 `build_query_fallback()` 钩子（基类默认返回空）＋ `_probe_query_reply()`；主查询族全部静默时，在同一次 checked probe 里再探一次备用族。AC 用 BB 子协议查询实现它；一旦 `_used_subprotocol` 置位就返回空，所以每连接最多多探一次。 |

### 为什么算"通用"而不是打补丁

上游的 `AC_MODEL_CAPABILITIES` 型号表只能覆盖"已经有人报过的型号/子类型"，
每来一个新的 BB-only 机型都要再补一行。这里的做法是在协议探测阶段**运行时**发现
"主族整体静默"，再由设备类提供候选的备用族；基类默认没有备用族，
其他设备的行为完全不变（失败路径和以前一样）。设备整体不可达时两族都不应答，
不会误判、不会切换，下次连接仍按主族探测。

## 本地验证

```
python -m pytest ./tests/   # 2026 passed
ruff check . && ruff format --check .
mypy midealan
```

三处修复都做了"回退源码即失败"的验证：去掉重试 → 8 个测试失败；
上限改回 600 秒 → 退避测试失败；回退备用族改动 → 4 个测试失败。
BB 回帧是用真机（223J6397）抓下来的三帧，解析结果 29.5 °C / 53 % / 25.5 °C 写进了测试。

## 怎么装到自己的 HA

### 方案 A：把修好的库装进 HA core 容器（最快，几分钟）

前提：能进 HA 容器。HAOS 用户装 `Advanced SSH & Web Terminal` 插件，并在插件配置里
关闭 protection mode（要用 `docker` 命令）。

```bash
# 1) 装 fork 版库（URL 里的 <sha> 用本分支最新提交，避免缓存）
docker exec homeassistant python3 -m uv pip install --system --reinstall --no-deps \
  "midea-lan @ https://github.com/Rbubblee/midea-lan/archive/refs/heads/personal/ac-probe-fallback-fix.zip"

# 如果容器里没有 uv 模块，就用 pip：
# docker exec homeassistant python3 -m pip install --no-cache-dir --force-reinstall --no-deps \
#   "midea-lan @ https://github.com/Rbubblee/midea-lan/archive/refs/heads/personal/ac-probe-fallback-fix.zip"

# 2) 确认装上了
docker exec homeassistant python3 -c \
  "import midealan; from midealan.device import MideaDevice; print(midealan.__version__, hasattr(MideaDevice, 'build_query_fallback'))"
# 期望输出：2026.9.1 True

# 3) 重启 HA core
ha core restart
```

说明：

- 本分支的 `midealan/version.py` 仍是 `2026.9.1`，与集成 `manifest.json` 里的
  `midea-lan==2026.9.1` 一致，所以 HA 启动时不会自己去 PyPI 重装覆盖
  （HA 只在 requirement 不满足时才安装）。
- HA core 更新（容器重建）后需要重跑一次；集成将来升级、manifest 要求新版本时也可能被覆盖，
  重跑同样的命令即可。
- 回滚：`docker exec homeassistant python3 -m uv pip install --system --reinstall "midea-lan==2026.9.1"`，
  然后 `ha core restart`。

### 方案 B：让 HA 自己装 fork 版（HACS 自定义仓库，适合长期自用）

1. fork 集成仓库 `wuwentao/midea_ac_lan` 到自己的账号；
2. 把它 `custom_components/midea_ac_lan/manifest.json` 里的
   `"midea-lan==2026.9.1"` 改成
   `"midea-lan @ https://github.com/Rbubblee/midea-lan/archive/refs/heads/personal/ac-probe-fallback-fix.zip"`；
3. HACS → 右上角菜单 → *Custom repositories* → 填你的 fork 地址、类型选 *Integration* → 添加，
   然后在 HACS 里用它替换原来的 `midea_ac_lan`（或在 `/config/custom_components/` 里直接替换该目录）；
4. 重启 HA。HA 处理 URL 形式的 requirement 时 `is_installed()` 永远返回 `False`，
   所以每次启动它都会用 uv 自己装一次这个 fork，不会被 PyPI 上的 `2026.9.1` 覆盖。

代价：以后用 HACS 升级集成时会覆盖 `manifest.json`，需要重新打这一行补丁（或把上游更新 merge 进你的 fork）。

### 验证修复是否生效

- 日志（`midealan` logger 调到 `debug`）应出现
  `no reply to [...], probing the alternative query family [...]`，随后设备 `available: True`；
- 实体 `climate.210006734918980_climate`、`sensor.210006734918980_indoor_temperature`、
  `sensor.210006734918980_indoor_humidity` 有值；
- 关机状态下 `current_energy_consumption` 为 `unknown` 属正常（其他 4 台同样如此）。

## 上游合并后怎么切回

上游把等价修复合并并发布新版本后：把集成升级到新版本（manifest 会要求新的
`midea-lan==…`），HA 会自己从 PyPI 装回官方版本，本分支即可停用。
