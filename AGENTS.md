# AGENTS.md

Guidance for AI coding agents (GitHub Copilot, Claude Code, Gemini CLI, Codex, etc.)
working in the `midea-lan` repository. This is the canonical instructions file;
`CLAUDE.md`, `GEMINI.md`, and `.github/copilot-instructions.md` point here.

`midea-lan` is a Python library to control Midea M-Smart appliances over the LAN
network. It handles device discovery, the encrypted Midea LAN protocol, and per-device
message encoding/decoding. Python ≥ 3.12 (CI tests 3.12–3.14).

## Build, test, lint

The dev environment uses [uv](https://docs.astral.sh/uv/). Bootstrap it with
`./scripts/setup.sh` (Linux/macOS/WSL2) or `scripts\setup.ps1` (Windows), which creates a
`.venv`, installs everything (runtime + dev + types) from `requirements-all.txt`, and
installs the [prek](https://github.com/j178/prek) hooks. Prefix commands with `uv run` to
use that environment.

- Run all tests: `uv run python -m pytest ./tests/`
- Run one test file: `uv run python -m pytest tests/devices/ac/message_ac_test.py`
- Run one test: `uv run python -m pytest tests/devices/ac/message_ac_test.py::TestACMessage::test_message_query -v`
- Coverage (as CI does): `uv run python -m pytest --cov=midealan --cov-report xml ./tests/`
- Lint/format/type-check all at once via `uv run prek run --all-files`. Individually:
  `uv run ruff check .`, `uv run ruff format .`, `uv run mypy midealan`,
  `uv run pylint --rcfile=pylintrc midealan`.

`ruff` uses `lint.select = ["ALL"]` with curated ignores in `ruff.toml`; `mypy` runs in
strict mode (`mypy.ini`). Fix all reported issues before committing — CI runs the full
prek suite across the OS/Python matrix and blocks merge on failure.

## Architecture

The protocol is split into three layers; understanding a feature usually means reading
across all three:

- **Transport / framing** (`device.py`, `packet_builder.py`, `security.py`, `crc8.py`):
  `MideaDevice` is a `threading.Thread` that owns the socket, handshake, auth (token/key),
  and the encrypt → frame → CRC pipeline. `LocalSecurity` implements V1/V2/V3 encryption.
- **Generic messages** (`message.py`): base classes `MessageRequest`, `MessageResponse`,
  `MessageBody`, `NewProtocolMessageBody`, plus `MessageType` and `ListTypes`. Every
  device message subclasses these.
- **Per-device packages** (`devices/<type>/`): one folder per appliance type, named by the
  device-type byte in hex (e.g. `ac`, `a1`, `e2`; types `< 0xA0` are prefixed with `x`,
  e.g. `x13`, `x40`). Each package has `__init__.py` (the device class) and `message.py`
  (that device's request/response messages).

Entry points: `discover.py` finds devices on the LAN; `devices/__init__.py`
`device_selector()` dynamically `import_module`s the right `devices/<type>` package and
instantiates its `MideaAppliance`. `cloud.py` retrieves token/key from Midea cloud
accounts. `cli.py` (`python3 -m midealan.cli` / `midealan`) and `library_test.py` are
user-facing harnesses.

## Conventions specific to this codebase

- **Adding/extending a device type**: create `devices/<hextype>/` matching the
  `device_selector` naming rule above. The device class extends `MideaDevice` and must be
  re-exported as `MideaAppliance` (see the `class MideaAppliance(MideaA1Device)` alias at
  the bottom of each `__init__.py`). Implement `build_query`, `process_message`, and
  `set_attribute`. Many devices add a `make_message_set` helper that `set_attribute` calls
  to assemble the outgoing frame, but it is a per-device convenience, not a required
  override — newer devices (e.g. `x9b`, `x9c`) build the set message inline in
  `set_attribute` instead. For a full, step-by-step walkthrough see
  [`docs/adding-a-new-device.md`](docs/adding-a-new-device.md) (and its `.zh-Hans.md`
  translation), which uses `0xD9` ([PR #175](https://github.com/wuwentao/midea-lan/pull/175))
  as its running example and `0x9B`
  ([PR #181](https://github.com/wuwentao/midea-lan/pull/181)) as a second worked example
  for richer devices (decoder-derived attribute enum, write-only/synthetic attributes,
  sub-command framing, range-checked numeric params, structured multi-step commands,
  V1/V2 superset decoding).
- **Attributes** are declared as a `DeviceAttributes(StrEnum)` per device and exposed
  through the `device.attributes` dict; state is never accessed by raw key elsewhere.
- **No magic numbers**: protocol offsets, lengths, and flag values are named module-level
  constants (see the block at the top of each `message.py` and `const.py`). Follow this
  when adding parsing logic; ruff's `PLR2004` enforces it outside `tests/`.
- **Device type registry**: register new appliance bytes in `const.py` `DeviceType` and,
  where relevant, `ListTypes` in `message.py`.
- **Tests** mirror the source tree under `tests/`, suffixed `_test.py`
  (e.g. `tests/devices/ac/message_ac_test.py`). Sample binary payloads live in
  `tests/responses/`. `tests/*` has relaxed ruff/mypy rules (asserts, private access, etc.).
  Added or changed executable code must have 100% Codecov patch coverage.
- **Commits** must follow Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`,
  `refactor:`, `test:`); commitlint/commitizen enforce this and CI validates PR messages.
  Do not commit directly to `main` (prek `no-commit-to-branch`).
- Recommended dev environment is **uv + a local `.venv`** (`./scripts/setup.sh` or
  `scripts\setup.ps1`); see `.github/CONTRIBUTING.md`.

## Pull request requirements

- Complete `.github/pull_request_template.md`; use N/A with a short reason when a
  link does not apply.
- PRs should link the exact supporting Lua file in
  [`wuwentao/midea-lua`](https://github.com/wuwentao/midea-lua) when it relies on
  a device protocol. If it is missing, follow that repository's README to download
  it, submit it to `midea-lua` first, and link the resulting PR. If no Lua protocol
  applies, explain why.
- PRs should link any related
  [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) issue, regardless of
  its title or change type; explain when no related issue exists.
- PRs should link a matching `midea_ac_lan` PR when they affect Home Assistant
  behavior or device support; explain when no integration PR is needed. Do not
  update the `midea-lan` version in
  `midea_ac_lan/custom_components/midea_ac_lan/manifest.json`; maintainers update
  it centrally after release.
- A merge does not trigger an immediate release. Maintainers accumulate changes,
  publish `midea-lan` manually on a periodic basis, and then synchronize
  `midea_ac_lan`.
- After GitHub Actions finish, verify 100% Codecov patch coverage and wait for the
  automatic CodeRabbit review. Address each actionable comment, reply in its
  thread with the fix and test evidence, and resolve the conversation before merge.

## Submitting issues and pull requests (AI agents)

Most issues and PRs here are now drafted with an AI agent. The agent MUST drive the
submission through the repository templates — not around them. Free-form,
AI-generated issue/PR text that skips the template is the single most common reason
reports are incomplete and get closed or stalled. Follow these rules:

- **Use the repository template as the outline, verbatim.** For issues, open one of
  the forms in `.github/ISSUE_TEMPLATE/` (bug or enhancement, in the submitter's
  language). For PRs, start from `.github/pull_request_template.md` and keep every
  heading and checklist item. Do not delete, rename, reorder, or replace sections
  with your own structure. Additional detail beyond the template is welcome, but it
  goes _after_ the template fields, not instead of them.
- **Fill every field; gather what is missing before asking.** For each field, first
  try to obtain the value yourself from the repo, git history, tests, `cli.py`
  (`uv run python -m midealan.cli -h`: `discover`, `decode`, `save`, `download`,
  `setattr`), `library_test.py`, or the `discover()` API. Only when a value genuinely
  cannot be obtained by the agent — device SN, a redacted on-device debug log, an
  official-app screenshot — explicitly ask the submitter to provide it. Never silently
  drop a field or invent a plausible-looking value.
- **`N/A` must carry a reason.** Use `N/A` only when a section truly does not apply,
  and add a short phrase explaining why (e.g. "N/A — tooling-only change, no device
  protocol"). An unexplained `N/A` or a blank field is treated as incomplete.
- **Lua protocol source (checklist).** When the change relies on a device protocol:
  1. Check [`wuwentao/midea-lua`](https://github.com/wuwentao/midea-lua) for the exact
     protocol file. If it already exists, link that file directly.
  2. If it is missing, guide the submitter to download it as documented in the
     `midea-lua` README, format it with StyLua (or the formatter that repo's README
     specifies), and open a `midea-lua` PR _first_. Link that PR here; land or
     reference it alongside this PR rather than pasting raw Lua into this repo.
  3. If no Lua protocol applies, use `N/A` with a one-line reason.
- **Redact secrets.** Never paste account credentials, tokens, keys, full device IDs,
  MAC addresses, or unredacted logs. Mask them (keep only what is needed to diagnose).
- **Cross-link the family.** Link the related
  [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) issue/PR and the
  `midea-lua` source as the template asks, so the three-repo change set stays
  traceable.

### Keep code consistent with what exists

When implementing a fix or feature, match the approach already in the codebase; do not
invent parallel styles:

- Follow the existing per-device layout, naming, and patterns (see "Adding/extending a
  device type" above and `docs/adding-a-new-device.md`). Reuse the established constant
  blocks, `DeviceAttributes(StrEnum)`, and message base classes rather than new ad-hoc
  shapes.
- **Avoid adding new files or new naming conventions** unless necessary. If a new file
  or pattern is genuinely required, say so in the PR and explain the reason and the
  benefit, so reviewers can weigh it against consistency.
- **Comment the key and divergent parts.** Where logic is non-obvious, differs notably
  from sibling devices, or encodes a protocol detail, add a short English comment and
  cite the referenced Lua field name / byte offset. This is what later edits rely on to
  avoid regressions or mis-edits.
