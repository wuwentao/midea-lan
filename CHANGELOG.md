# Changelog

## [2026.9.0](https://github.com/wuwentao/midea-lan/compare/v2026.8.0...v2026.9.0) (2026-09-02)


### ⚠ BREAKING CHANGES

* **ac:** removes NewProtocolSelfCleanQuery subclass

### Features

* **ac:** run B5 capability queries once and publish results to HA ([#63](https://github.com/wuwentao/midea-lan/issues/63)) ([874e3fd](https://github.com/wuwentao/midea-lan/commit/874e3fdc74153f5d4f5617ad6c9aa95331ccce49))
* **ac:** support iECO query and set ([#70](https://github.com/wuwentao/midea-lan/issues/70)) ([89d7dfe](https://github.com/wuwentao/midea-lan/commit/89d7dfea6c9c6e732a0a31163539979f7918b24c))
* **bf:** implement full BF microwave steam oven message parsing and … ([#23](https://github.com/wuwentao/midea-lan/issues/23)) ([a8d918f](https://github.com/wuwentao/midea-lan/commit/a8d918f1c4e34a1e7e4e9e85e5296eb25f2a2d7c))
* **c3:** expose outdoor-unit runtime telemetry as device attributes ([#53](https://github.com/wuwentao/midea-lan/issues/53)) ([4b91c8f](https://github.com/wuwentao/midea-lan/commit/4b91c8f44cb7e3ed4d4af180e7ddf411c8bec8f1))
* **c3:** expose outdoor-unit telemetry as device attributes ([#58](https://github.com/wuwentao/midea-lan/issues/58)) ([b25433b](https://github.com/wuwentao/midea-lan/commit/b25433b41a24d60115ebc0473ca73acf88d5f920))
* **c3:** parse the MSG_TYPE_UP_UNITPARA notify ([#55](https://github.com/wuwentao/midea-lan/issues/55)) ([85940db](https://github.com/wuwentao/midea-lan/commit/85940dbfb7aba61d179a2e2a7c39577366a2ca44))
* **cd:** support extended water heater protocol ([#61](https://github.com/wuwentao/midea-lan/issues/61)) ([e2a6fd2](https://github.com/wuwentao/midea-lan/commit/e2a6fd2ae31ce41e5f3275229d8858d00039d0b3))


### Bug Fixes

* **ac:** correct rate_select gears and set path for reported levels ([#65](https://github.com/wuwentao/midea-lan/issues/65)) ([38c4ed0](https://github.com/wuwentao/midea-lan/commit/38c4ed0a6ec47d7238813a2f86fecaada11984d9))
* **ac:** guard XA1Body parsing against short notify bodies ([#42](https://github.com/wuwentao/midea-lan/issues/42)) ([460063f](https://github.com/wuwentao/midea-lan/commit/460063fc8eb4c231dc837446b12fdec2b12cc7fd))
* **ac:** keep unit on when a mode change is followed by a temperature write ([#12](https://github.com/wuwentao/midea-lan/issues/12)) ([27ddba1](https://github.com/wuwentao/midea-lan/commit/27ddba1b00c6681fddc7e605e8f3e50b2454e78d)), closes [#495](https://github.com/wuwentao/midea-lan/issues/495)
* **ac:** remove error_code_query from default list ([#64](https://github.com/wuwentao/midea-lan/issues/64)) ([ba48fb9](https://github.com/wuwentao/midea-lan/commit/ba48fb96524fe37ab6acf125fc1d6fe1ee958474))
* **b0:** correct status labels 0x02/0x03 on subtype zero ([#14](https://github.com/wuwentao/midea-lan/issues/14)) ([a0bf866](https://github.com/wuwentao/midea-lan/commit/a0bf866b6ba39c7d17b1ae5b8cee491fe78f026d))
* **c3:** align four X10 UnitPara offsets with the official lua protocol ([#52](https://github.com/wuwentao/midea-lan/issues/52)) ([aeee249](https://github.com/wuwentao/midea-lan/commit/aeee249dc3abf17bc8455ce30ce40fd61f69e784))
* **c3:** correct outdoor fan speed parsing and add regression coverage ([#51](https://github.com/wuwentao/midea-lan/issues/51)) ([e4a8e34](https://github.com/wuwentao/midea-lan/commit/e4a8e345d11a52020dae7c2bec6594c37f4815a5))
* **c3:** shift 32-bit energy counters by 24, not 32 ([#54](https://github.com/wuwentao/midea-lan/issues/54)) ([2008d17](https://github.com/wuwentao/midea-lan/commit/2008d1710e9be9b530fcccff1206d1110132d4f3))
* **cd:** don't let SET echo clobber power state ([#11](https://github.com/wuwentao/midea-lan/issues/11)) ([95fe914](https://github.com/wuwentao/midea-lan/commit/95fe914bde5e76bc0b3f2862ea311ccabd8877f8))
* close socket catch error ([#28](https://github.com/wuwentao/midea-lan/issues/28)) ([f72c482](https://github.com/wuwentao/midea-lan/commit/f72c48215a52cb598908465a60cf041cbd23cf3c))
* **cloud:** support legacy lua download for MideaAirCloud ([#10](https://github.com/wuwentao/midea-lan/issues/10)) ([f47c3a0](https://github.com/wuwentao/midea-lan/commit/f47c3a0d8bbfa873e04fb5d6d6b62a676fb395f8))
* **cloud:** use the v2 getToken endpoint for the Meiju cloud ([#44](https://github.com/wuwentao/midea-lan/issues/44)) ([67f1eda](https://github.com/wuwentao/midea-lan/commit/67f1eda757fad4a4a4fd6e8457ee8de87452578b))
* **device:** recover from a device that supports no query protocol ([#41](https://github.com/wuwentao/midea-lan/issues/41)) ([b38e556](https://github.com/wuwentao/midea-lan/commit/b38e556bb1b513cfeb06f4654cb934ba1007c540))
* **e2:** make precision_halves symmetric so target temperature round-trips ([#19](https://github.com/wuwentao/midea-lan/issues/19)) ([f801dca](https://github.com/wuwentao/midea-lan/commit/f801dcaf0d17007ad527bfc07c96b84e43a9fd52))
* **e2:** warn and ignore old-protocol attributes MessageSet cannot carry ([#17](https://github.com/wuwentao/midea-lan/issues/17)) ([6f351c9](https://github.com/wuwentao/midea-lan/commit/6f351c961b5328dd7dfc894931e6868c6d55e6c8))
* **ed:** cancel queued tea bar heating after filling ([#5](https://github.com/wuwentao/midea-lan/issues/5)) ([2b8bec7](https://github.com/wuwentao/midea-lan/commit/2b8bec7baf1c3e1b66aa2589cb6436d892eb688b))
* **fa:** support extended fan modes ([#50](https://github.com/wuwentao/midea-lan/issues/50)) ([7df6292](https://github.com/wuwentao/midea-lan/commit/7df62922fd8621e5f45877a7f802a57634725b70))


### Documentation

* document cloud download CLI ([#22](https://github.com/wuwentao/midea-lan/issues/22)) ([75f1450](https://github.com/wuwentao/midea-lan/commit/75f1450c80df36840b34090307cbc4798aa2eee6))


### Miscellaneous Chores

* release 2026.9.0 ([#76](https://github.com/wuwentao/midea-lan/issues/76)) ([370a717](https://github.com/wuwentao/midea-lan/commit/370a717520273891c0fa22f939cc808885f3e425))


### Code Refactoring

* **ac:** merge NewProtocolQuery and add customize capabilities override ([#66](https://github.com/wuwentao/midea-lan/issues/66)) ([74ff962](https://github.com/wuwentao/midea-lan/commit/74ff9628bd52161145d49d5ae115f6479f25bbde))

## [2026.8.0](https://github.com/wuwentao/midea-lan/compare/midea-lan-v2026.7.0...midea-lan-v2026.8.0) (2026-08-12)


### Features

* **ac:** gate rate_select query behind b5_electricity capability ([#632](https://github.com/wuwentao/midea-lan/issues/632)) ([30bd23b](https://github.com/wuwentao/midea-lan/commit/30bd23bdf427b5fe109d567011d3825f1d046044))
* **b1:** decode X01 fallback query responses ([#633](https://github.com/wuwentao/midea-lan/issues/633)) ([659aa2a](https://github.com/wuwentao/midea-lan/commit/659aa2adc4e647d0059fc801e2bbf24d2663c2a8))
* **ed:** support subtype 395 tea bar appliances ([#628](https://github.com/wuwentao/midea-lan/issues/628)) ([b4c811b](https://github.com/wuwentao/midea-lan/commit/b4c811b812de0ee49fe65a5fae83367ce26de741))
* midea-lan init commit ([6ae208d](https://github.com/wuwentao/midea-lan/commit/6ae208de7b755e41d9feb249c4d7f9fabb9c87b0))


### Bug Fixes

* **b0:** ignore 31 body on subtype zero devices ([#629](https://github.com/wuwentao/midea-lan/issues/629)) ([569cc83](https://github.com/wuwentao/midea-lan/commit/569cc83d8fcc94861ee3931af34e1d538e146195))

## Changelog
