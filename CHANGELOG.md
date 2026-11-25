# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [2026.11.0](https://github.com/wuwentao/midea-lan/compare/v2026.10.0...v2026.11.0) (2026-11-18)

### Features
- **x44:** Add smart panel screen query and control [#252](https://github.com/wuwentao/midea-lan/pull/252) by [@1021683053](https://github.com/1021683053) ([ada76e3](https://github.com/wuwentao/midea-lan/commit/ada76e326c3f932da6d2bbf128c67f4697e98def))
- **toshiba:** Add shared frame codec and protocol support [#224](https://github.com/wuwentao/midea-lan/pull/224) by [@wuwentao](https://github.com/wuwentao) ([e188e28](https://github.com/wuwentao/midea-lan/commit/e188e287f169aeac488ef216c043107f5390f97a))
- **db:** Support Toshiba washer status [#234](https://github.com/wuwentao/midea-lan/pull/234) by [@wuwentao](https://github.com/wuwentao) ([8d4d22f](https://github.com/wuwentao/midea-lan/commit/8d4d22f2b11f8bf69d9b265e23485722bf5ae91e))
- **x13:** Add fan light support for model M0200008 [#246](https://github.com/wuwentao/midea-lan/pull/246) by [@zengyu-dev](https://github.com/zengyu-dev) ([56f42c3](https://github.com/wuwentao/midea-lan/commit/56f42c3254f8aae779a85c209cd1a3b75501bbbe))
- **ac:** Support Toshiba status protocol [#235](https://github.com/wuwentao/midea-lan/pull/235) by [@wuwentao](https://github.com/wuwentao) ([6d3cec9](https://github.com/wuwentao/midea-lan/commit/6d3cec9b8f1a70044b65454d2e343a1f0bfabfb3))
- **bf:** Support Toshiba appliance status [#236](https://github.com/wuwentao/midea-lan/pull/236) by [@wuwentao](https://github.com/wuwentao) ([485a223](https://github.com/wuwentao/midea-lan/commit/485a223352b57c4cc90a41d52046578960d186c7))
- **ca:** Support Toshiba refrigerator status [#237](https://github.com/wuwentao/midea-lan/pull/237) by [@wuwentao](https://github.com/wuwentao) ([8010dd2](https://github.com/wuwentao/midea-lan/commit/8010dd2cf6ca8547cc9a92c43c1ac4a7da0fd621))
- **ea:** Support Toshiba rice cooker status [#238](https://github.com/wuwentao/midea-lan/pull/238) by [@wuwentao](https://github.com/wuwentao) ([01bd2a0](https://github.com/wuwentao/midea-lan/commit/01bd2a0a07889476d483da0b1feec60b9495e45f))
- **x51:** Support Toshiba appliance status [#239](https://github.com/wuwentao/midea-lan/pull/239) by [@wuwentao](https://github.com/wuwentao) ([8b1da8d](https://github.com/wuwentao/midea-lan/commit/8b1da8da4b417a3e13af5e99b23e726aaa04bd03))
- **da:** Support Toshiba washer status [#240](https://github.com/wuwentao/midea-lan/pull/240) by [@wuwentao](https://github.com/wuwentao) ([061df03](https://github.com/wuwentao/midea-lan/commit/061df03f27a409bddaa5f5f50e371de5c00098b5))
- **ac:** Add electric aux-heat (PTC) control via tri-state aux_heat_mode [#227](https://github.com/wuwentao/midea-lan/pull/227) by [@wuwentao](https://github.com/wuwentao) ([e75080b](https://github.com/wuwentao/midea-lan/commit/e75080bf6cf5d5e5cd2554da8421dd9fa2d508c8))
- **ac:** Expose person flags through capability queries [#263](https://github.com/wuwentao/midea-lan/pull/263) by [@yezhiming1](https://github.com/yezhiming1) ([4007aca](https://github.com/wuwentao/midea-lan/commit/4007acaf44cc2cee3426b955b795505360558313))
- **ac:** Parse BB X11 humidify switch and target humidity [#268](https://github.com/wuwentao/midea-lan/pull/268) by [@yrwd999](https://github.com/yrwd999) ([6b122d8](https://github.com/wuwentao/midea-lan/commit/6b122d86c669100c4bbbd0d4d443374077907b4b))
- **db:** Decode v41 washer-dryer status fields [#273](https://github.com/wuwentao/midea-lan/pull/273) by [@Cerso](https://github.com/Cerso) ([1494912](https://github.com/wuwentao/midea-lan/commit/14949122f46123274bc782847a2afab192e96fae))
- **discover:** Surface unsupported devices with a support verdict [#277](https://github.com/wuwentao/midea-lan/pull/277) by [@wuwentao](https://github.com/wuwentao) ([534bfed](https://github.com/wuwentao/midea-lan/commit/534bfed8a83d4d0ba9950db76386266bbe09df69))
- **x17:** Add electric clothes-drying rack device support [#278](https://github.com/wuwentao/midea-lan/pull/278) by [@wuwentao](https://github.com/wuwentao) ([15d16b7](https://github.com/wuwentao/midea-lan/commit/15d16b7d8aac7b3e264e0b52e29c3af3a011f93d))
- **x10:** Add power-only appliance device support [#279](https://github.com/wuwentao/midea-lan/pull/279) by [@wuwentao](https://github.com/wuwentao) ([a44c406](https://github.com/wuwentao/midea-lan/commit/a44c40675947174de20c473950c59c38a4de569b))
- **x14:** Add electric curtain / blind motor device support [#280](https://github.com/wuwentao/midea-lan/pull/280) by [@wuwentao](https://github.com/wuwentao) ([e6a4aad](https://github.com/wuwentao/midea-lan/commit/e6a4aad2bdd68571307c5151d6e87e98472843b2))
- **x9a:** Add microwave / steam-bake oven device support [#281](https://github.com/wuwentao/midea-lan/pull/281) by [@wuwentao](https://github.com/wuwentao) ([0735367](https://github.com/wuwentao/midea-lan/commit/073536793531d59117ddfe4827cae1607ef43c73))
- **b2:** Add steam box / steam oven device support [#282](https://github.com/wuwentao/midea-lan/pull/282) by [@wuwentao](https://github.com/wuwentao) ([2177e18](https://github.com/wuwentao/midea-lan/commit/2177e1866067588f8571a4d9f9e49845fe1e98af))
- **eb:** Add steam / warming cooking appliance device support [#283](https://github.com/wuwentao/midea-lan/pull/283) by [@wuwentao](https://github.com/wuwentao) ([7f28f08](https://github.com/wuwentao/midea-lan/commit/7f28f0895edf5cff4bf8240d8a48d096d7775647))
- **ef:** Add beverage / drink maker device support [#284](https://github.com/wuwentao/midea-lan/pull/284) by [@wuwentao](https://github.com/wuwentao) ([44a2ed4](https://github.com/wuwentao/midea-lan/commit/44a2ed4b795cc8d19130e66290224e5c4a409b26))
- **e7:** Add steam / warming cooking appliance device support [#287](https://github.com/wuwentao/midea-lan/pull/287) by [@wuwentao](https://github.com/wuwentao) ([232efee](https://github.com/wuwentao/midea-lan/commit/232efeefd66232ac811a21a3ef0cba33cd4290f1))
- **f1:** Add tea / beverage brewer device support [#285](https://github.com/wuwentao/midea-lan/pull/285) by [@wuwentao](https://github.com/wuwentao) ([9357beb](https://github.com/wuwentao/midea-lan/commit/9357bebb1117584d65c82ccc5e7fd8d78a197fac))
- **e9:** Add bread / baking machine device support [#286](https://github.com/wuwentao/midea-lan/pull/286) by [@wuwentao](https://github.com/wuwentao) ([add6c9c](https://github.com/wuwentao/midea-lan/commit/add6c9c68424180d3f57ed45a63870c8a38986ce))
- **x70:** Add seasoning / spice dispenser device support [#288](https://github.com/wuwentao/midea-lan/pull/288) by [@wuwentao](https://github.com/wuwentao) ([95e4457](https://github.com/wuwentao/midea-lan/commit/95e4457ce3f822e7c7f0c4fc930ceb122df1dcdd))
- **b7:** Add smart gas stove device support (read-only status + simple controls) [#289](https://github.com/wuwentao/midea-lan/pull/289) by [@wuwentao](https://github.com/wuwentao) ([3605d50](https://github.com/wuwentao/midea-lan/commit/3605d50a25049433e85954de7966dbeb78dfa6f4))
- **db:** Add MD10L7PRO to the v41 read-only profile [#274](https://github.com/wuwentao/midea-lan/pull/274) by [@wuwentao](https://github.com/wuwentao) ([74da45a](https://github.com/wuwentao/midea-lan/commit/74da45afaca5b8662f1a7c52a4a12ef3000e3846))
- **c3:** Support native 17100007 controls and energy telemetry [#261](https://github.com/wuwentao/midea-lan/pull/261) by [@lavdrimismajili](https://github.com/lavdrimismajili) ([2b8779c](https://github.com/wuwentao/midea-lan/commit/2b8779cfd7ac722678c882c021e9809fe75e04be))
- **dc:** Detect extended dryers and add steam/material/season controls [#294](https://github.com/wuwentao/midea-lan/pull/294) by [@wuwentao](https://github.com/wuwentao) ([6aa5463](https://github.com/wuwentao/midea-lan/commit/6aa5463cbe65eaf27f0d1a70c0cd8426b801dd43))
- **e1:** Expose model-specific capabilities [#264](https://github.com/wuwentao/midea-lan/pull/264) by [@wuwentao](https://github.com/wuwentao) ([890e0fc](https://github.com/wuwentao/midea-lan/commit/890e0fc69f74d4a888c693ad05d03dcfda4eff61))
- Parse and log 0xA0 appliance-info response body [#303](https://github.com/wuwentao/midea-lan/pull/303) by [@wuwentao](https://github.com/wuwentao) ([865b94d](https://github.com/wuwentao/midea-lan/commit/865b94dfb163d70ab265cb21b3d55c541534c9b9))
- **cli:** Add info command to list cloud account appliances [#304](https://github.com/wuwentao/midea-lan/pull/304) by [@wuwentao](https://github.com/wuwentao) ([477211a](https://github.com/wuwentao/midea-lan/commit/477211a21aff243b3af069ff7f010227f77ef0e4))
- **cli:** Surface discovered subtype/identity and reuse it on discover [#305](https://github.com/wuwentao/midea-lan/pull/305) by [@wuwentao](https://github.com/wuwentao) ([1f50843](https://github.com/wuwentao/midea-lan/commit/1f50843e372fb767d7d5464f8296cf12479d38a9))
- **a1:** Add group-one compressor telemetry [#302](https://github.com/wuwentao/midea-lan/pull/302) by [@wuwentao](https://github.com/wuwentao) ([5f0ea3a](https://github.com/wuwentao/midea-lan/commit/5f0ea3a96b09ba8f03e0f0dce5dbd9d96d3f8eff))
- **x9b:** Support extensible 700ZG249 protocol profile [#291](https://github.com/wuwentao/midea-lan/pull/291) by [@wuwentao](https://github.com/wuwentao) ([99ea924](https://github.com/wuwentao/midea-lan/commit/99ea9242fb1736fae3bf9f8a837685c6d6c822d5))

### Bug Fixes
- **cd:** Decode 2530001N signed temperatures [#230](https://github.com/wuwentao/midea-lan/pull/230) by [@wuwentao](https://github.com/wuwentao) ([898c12d](https://github.com/wuwentao/midea-lan/commit/898c12d46256ac3a6006a5e7c58d130caf06945c))
- **e3:** Sign dayReportV2 proxy requests [#247](https://github.com/wuwentao/midea-lan/pull/247) by [@skyel1u](https://github.com/skyel1u) ([654e92b](https://github.com/wuwentao/midea-lan/commit/654e92bbaadfbeead05fdab5fd582b75a0dd3231))
- **security:** Count the signature in the 8370 length when no padding is needed [#251](https://github.com/wuwentao/midea-lan/pull/251) by [@connabyss](https://github.com/connabyss) ([31410e1](https://github.com/wuwentao/midea-lan/commit/31410e13137df4729263cefa7a5e2b400e781236))
- **cd:** Decode RSJRAC08 temperatures like 2530001N [#259](https://github.com/wuwentao/midea-lan/pull/259) by [@CoRfr](https://github.com/CoRfr) ([00fd6a6](https://github.com/wuwentao/midea-lan/commit/00fd6a6a91240441d97ff9e950462344ef9f713c))
- **cd:** Preserve clock fields in control writes [#249](https://github.com/wuwentao/midea-lan/pull/249) by [@wuwentao](https://github.com/wuwentao) ([9939277](https://github.com/wuwentao/midea-lan/commit/9939277d468624e9f44152c402d6feedeaa5f49b))
- **ci:** Preserve main Codecov branch attribution [#262](https://github.com/wuwentao/midea-lan/pull/262) by [@wuwentao](https://github.com/wuwentao) ([ae46df6](https://github.com/wuwentao/midea-lan/commit/ae46df67427795f47cd7fa19d90d7f6cf9095499))
- **ac:** Prefer C0 display state for affected models [#248](https://github.com/wuwentao/midea-lan/pull/248) by [@wuwentao](https://github.com/wuwentao) ([30a69fb](https://github.com/wuwentao/midea-lan/commit/30a69fbe8c70a36513f79b2622668f3b6de0053a))
- **db:** Preserve confirmed parameters when starting the v33 washer [#275](https://github.com/wuwentao/midea-lan/pull/275) by [@wuwentao](https://github.com/wuwentao) ([7305c12](https://github.com/wuwentao/midea-lan/commit/7305c123e8f881755bd04d3cf2d438152f733dfb))
- **ce:** Support compact status and timer protocol [#266](https://github.com/wuwentao/midea-lan/pull/266) by [@wuwentao](https://github.com/wuwentao) ([2d11871](https://github.com/wuwentao/midea-lan/commit/2d118718ac50cb42cd1af47ae063c4f3e4f965ea))
- **e1:** Encode door auto-open as tri-state [#297](https://github.com/wuwentao/midea-lan/pull/297) by [@wuwentao](https://github.com/wuwentao) ([dbac8b6](https://github.com/wuwentao/midea-lan/commit/dbac8b69387d32f43227033d0716f9dc2124bd6c))
- **e3:** Route subtypes 38 and 39 through legacy protocol [#299](https://github.com/wuwentao/midea-lan/pull/299) by [@wuwentao](https://github.com/wuwentao) ([10138bb](https://github.com/wuwentao/midea-lan/commit/10138bbff2ef45a7738768480df7113b72ff3cde))
- **c3:** Decode ECO reply mistagged as silence body type 0x05 [#301](https://github.com/wuwentao/midea-lan/pull/301) by [@wuwentao](https://github.com/wuwentao) ([718b9f8](https://github.com/wuwentao/midea-lan/commit/718b9f84932e20dec1cff0beb11ff39f2caa9cd2))
- **c3:** Decode signed legacy unit temperatures [#272](https://github.com/wuwentao/midea-lan/pull/272) by [@przymul](https://github.com/przymul) ([980b7b8](https://github.com/wuwentao/midea-lan/commit/980b7b8a887012ba5003f42cb6b02dce88819924))
- **fd:** Support protocol-specific humidifier layouts [#265](https://github.com/wuwentao/midea-lan/pull/265) by [@wuwentao](https://github.com/wuwentao) ([a7c496c](https://github.com/wuwentao/midea-lan/commit/a7c496c5e1eea9b0a978acac8c56c7b8ef6560f6))

### Refactor
- **db:** Tag the recognized profile and unify the v33 gate [#295](https://github.com/wuwentao/midea-lan/pull/295) by [@wuwentao](https://github.com/wuwentao) ([f187a42](https://github.com/wuwentao/midea-lan/commit/f187a429907430a72d0819a0f8d162e1e018bb18))

### Documentation
- Add AI-agent issue/PR rules and issue templates [#270](https://github.com/wuwentao/midea-lan/pull/270) by [@wuwentao](https://github.com/wuwentao) ([abab85b](https://github.com/wuwentao/midea-lan/commit/abab85b7397a271755468a0bb9765a2e48600d1a))
- Require full URLs for cross-repo issue/PR refs [#276](https://github.com/wuwentao/midea-lan/pull/276) by [@wuwentao](https://github.com/wuwentao) ([7f26dc3](https://github.com/wuwentao/midea-lan/commit/7f26dc362253e7cba53b13f5b101c43f774a278e))
- Add README navigation and sponsorship links [#296](https://github.com/wuwentao/midea-lan/pull/296) by [@wuwentao](https://github.com/wuwentao) ([02caa12](https://github.com/wuwentao/midea-lan/commit/02caa12a750ab650be942789c931a9193de64e24))

### Testing
- **c1:** Reach full branch coverage [#256](https://github.com/wuwentao/midea-lan/pull/256) by [@wuwentao](https://github.com/wuwentao) ([4193037](https://github.com/wuwentao/midea-lan/commit/4193037ac659326e3d4f2ea941367d6ba818ad4f))
- **ac:** Reach full branch coverage [#257](https://github.com/wuwentao/midea-lan/pull/257) by [@wuwentao](https://github.com/wuwentao) ([ff3ba1f](https://github.com/wuwentao/midea-lan/commit/ff3ba1f68d2906a94a1a10f022aef323a7b45aad))
- **coverage:** Reach full branch coverage [#258](https://github.com/wuwentao/midea-lan/pull/258) by [@wuwentao](https://github.com/wuwentao) ([e0a148f](https://github.com/wuwentao/midea-lan/commit/e0a148f85b3dcd21cb572eeba65b0d342b05d647))

### Miscellaneous Tasks
- Strengthen pull request quality gates [#255](https://github.com/wuwentao/midea-lan/pull/255) by [@wuwentao](https://github.com/wuwentao) ([eeb1df4](https://github.com/wuwentao/midea-lan/commit/eeb1df47a835c7d3897168bb3a7da0c9d30238ae))
## [2026.10.0](https://github.com/wuwentao/midea-lan/compare/v2026.9.2...v2026.10.0) (2026-10-22)

### Features
- **ac:** Expose defrost state from group 5 data [#170](https://github.com/wuwentao/midea-lan/pull/170) by [@cassus](https://github.com/cassus) ([a708fd8](https://github.com/wuwentao/midea-lan/commit/a708fd84d6cb0b38ec03be135afcb70951469959))
- **ac:** Set countdown timers over LAN and keep them on routine commands [#186](https://github.com/wuwentao/midea-lan/pull/186) by [@cassus](https://github.com/cassus) ([4626bc9](https://github.com/wuwentao/midea-lan/commit/4626bc928afa10cb08f6517c7d0cdadb6e2ee134))
- **d9:** Add combined washer/dryer device support [#175](https://github.com/wuwentao/midea-lan/pull/175) by [@wuwentao](https://github.com/wuwentao) ([8819a49](https://github.com/wuwentao/midea-lan/commit/8819a49d010d7200981add7318e3b36068f6aea0))
- **x9b:** Add 0x9B microwave-steam-convection oven support [#181](https://github.com/wuwentao/midea-lan/pull/181) by [@wuwentao](https://github.com/wuwentao) ([873994d](https://github.com/wuwentao/midea-lan/commit/873994d93a91e047f2179f1843eac6526164b22f))
- **ca:** Expose read-only general status diagnostic flags [#187](https://github.com/wuwentao/midea-lan/pull/187) by [@yezhiming1](https://github.com/yezhiming1) ([4fb36e1](https://github.com/wuwentao/midea-lan/commit/4fb36e1ad143f60135f4b3ce894421965ba6cb16))
- **x9c:** Add 0x9C integrated kitchen appliance support [#179](https://github.com/wuwentao/midea-lan/pull/179) by [@wuwentao](https://github.com/wuwentao) ([5473e98](https://github.com/wuwentao/midea-lan/commit/5473e989326e112b424f6c87202cefc64984c145))
- **ac:** Read live state and dual-path temperatures from the 0x7e payload [#191](https://github.com/wuwentao/midea-lan/pull/191) by [@jazzzzmaybe](https://github.com/jazzzzmaybe) ([27b0312](https://github.com/wuwentao/midea-lan/commit/27b0312ee3ad79ea8ba0304be258cbb5f0238e9e))
- **ed:** Expand water purifier state parsing and add heat control [#193](https://github.com/wuwentao/midea-lan/pull/193) by [@jazzzzmaybe](https://github.com/jazzzzmaybe) ([c666b4d](https://github.com/wuwentao/midea-lan/commit/c666b4d669f11fe34a6e42b95a572692193b61e1))
- **device:** Expose sn8, manufacturer_code and cloud_name [#204](https://github.com/wuwentao/midea-lan/pull/204) by [@wuwentao](https://github.com/wuwentao) ([88128a0](https://github.com/wuwentao/midea-lan/commit/88128a0ec788e27eb34b19a8dd7499e98fa1b41b))
- **cloud:** Add Toshiba IOLife support [#205](https://github.com/wuwentao/midea-lan/pull/205) by [@wuwentao](https://github.com/wuwentao) ([6ebfd68](https://github.com/wuwentao/midea-lan/commit/6ebfd685cdf5e0abc0beb98dc0243afd49e7ef2b))
- **ed:** Add faucet gear writes for Midea MRO1012-R (632009EN) [#201](https://github.com/wuwentao/midea-lan/pull/201) by [@jazzzzmaybe](https://github.com/jazzzzmaybe) ([2c09489](https://github.com/wuwentao/midea-lan/commit/2c09489fed84078d0590c28907c5a0bf9d3be933))
- **e1:** Add cancel, delayed start and door auto-open [#207](https://github.com/wuwentao/midea-lan/pull/207) by [@marcoschicote](https://github.com/marcoschicote) ([2ac5fbe](https://github.com/wuwentao/midea-lan/commit/2ac5fbec6c5207ac7b090f756d9468a51da5845d))
- **e1:** Expose readable settings for the wash parameters [#213](https://github.com/wuwentao/midea-lan/pull/213) by [@marcoschicote](https://github.com/marcoschicote) ([da17976](https://github.com/wuwentao/midea-lan/commit/da17976948dabeaed8caf22f727609cf9382ea5c))
- **cloud:** Add TSmartLife support for Toshiba appliances [#198](https://github.com/wuwentao/midea-lan/pull/198) by [@jaspweowaale](https://github.com/jaspweowaale) ([6748eb6](https://github.com/wuwentao/midea-lan/commit/6748eb6266eb756e038faf5d9024428aa94820ab))
- **discover:** Also receive device broadcasts on fixed ports 7083/15000 [#222](https://github.com/wuwentao/midea-lan/pull/222) by [@wuwentao](https://github.com/wuwentao) ([ff20599](https://github.com/wuwentao/midea-lan/commit/ff20599d9d85524a073484a6895cd5ec1e04d283))
- **db:** Add verified washer controls and completion reservations [#206](https://github.com/wuwentao/midea-lan/pull/206) by [@cloverstd](https://github.com/cloverstd) ([44a6b83](https://github.com/wuwentao/midea-lan/commit/44a6b83d0921b09cf062a72c2fa345f0d204a5bc))
- **dc:** Add verified dryer controls and completion reservations [#214](https://github.com/wuwentao/midea-lan/pull/214) by [@cloverstd](https://github.com/cloverstd) ([41e4431](https://github.com/wuwentao/midea-lan/commit/41e4431149f3af7b48ffd3cdcc125880310a3a4f))
- **db:** Support v41 status profile [#223](https://github.com/wuwentao/midea-lan/pull/223) by [@wuwentao](https://github.com/wuwentao) ([23e9447](https://github.com/wuwentao/midea-lan/commit/23e9447013f425bbd0076764e2ed792154f46e21))

### Bug Fixes
- **cloud:** Redact token/key from getToken debug logs [#173](https://github.com/wuwentao/midea-lan/pull/173) by [@wuwentao](https://github.com/wuwentao) ([626ec18](https://github.com/wuwentao/midea-lan/commit/626ec18a6f46133cd100ef42d5bbe24d4cf1cf5e))
- **cloud:** Encode account password as UTF-8 to allow non-ASCII passwords [#174](https://github.com/wuwentao/midea-lan/pull/174) by [@wuwentao](https://github.com/wuwentao) ([7248c66](https://github.com/wuwentao/midea-lan/commit/7248c6669058375f842e9545fd3d2d3c9d0c57df))
- **device:** Publish availability when the active socket closes [#188](https://github.com/wuwentao/midea-lan/pull/188) by [@yezhiming1](https://github.com/yezhiming1) ([09f4374](https://github.com/wuwentao/midea-lan/commit/09f4374551f3037912a7e2b1cff236f028212f58))
- **ca:** Derive 310A2111 flex-zone mode in attributes [#190](https://github.com/wuwentao/midea-lan/pull/190) by [@yezhiming1](https://github.com/yezhiming1) ([93a5834](https://github.com/wuwentao/midea-lan/commit/93a58347c0590e32d986657c4cc3065dd396b1de))
- **ac:** Only publish temperature limits when they change [#203](https://github.com/wuwentao/midea-lan/pull/203) by [@wuwentao](https://github.com/wuwentao) ([3e47fff](https://github.com/wuwentao/midea-lan/commit/3e47fff3aaec7e38c40898130ba8dc8f01792fd3))
- **cd:** Decode RSJ000CB mixed sensor temperatures [#197](https://github.com/wuwentao/midea-lan/pull/197) by [@wuwentao](https://github.com/wuwentao) ([1539bc2](https://github.com/wuwentao/midea-lan/commit/1539bc2a72e0c619dd456babe85bcc4fc2a7f443))
- **c3:** Parse 2010 temperature telemetry by [@jontofront](https://github.com/jontofront) ([7bf6517](https://github.com/wuwentao/midea-lan/commit/7bf65176cdfc8dbd68f3c1483dcfc30af8d8d39e))
- **device:** Pace periodic status queries [#209](https://github.com/wuwentao/midea-lan/pull/209) by [@wuwentao](https://github.com/wuwentao) ([f2b8394](https://github.com/wuwentao/midea-lan/commit/f2b8394ffd97bdb7d3d55cce374e31e606b4ce88))
- **cloud:** Log MideaAirCloud getToken errors with warnging message [#216](https://github.com/wuwentao/midea-lan/pull/216) by [@wuwentao](https://github.com/wuwentao) ([30eefb9](https://github.com/wuwentao/midea-lan/commit/30eefb94df778661666aec3811e4bc36d3964752))
- **cloud:** Download MideaAirCloud lua via luaGetCbc with legacy fallback [#218](https://github.com/wuwentao/midea-lan/pull/218) by [@wuwentao](https://github.com/wuwentao) ([a751b23](https://github.com/wuwentao/midea-lan/commit/a751b232b3f1eb59a2f9fbff79b21732bf9c2fc6))
- **ac:** Probe an alternative query family before giving up [#658](https://github.com/wuwentao/midea-lan/pull/658) [#113](https://github.com/wuwentao/midea-lan/pull/113) by [@Rbubblee](https://github.com/Rbubblee) ([9d7543d](https://github.com/wuwentao/midea-lan/commit/9d7543d3510b8f2d9bcbf478c655de21ccc680a0))
- **cd:** Support 2530001N temperatures and active modes [#225](https://github.com/wuwentao/midea-lan/pull/225) by [@wuwentao](https://github.com/wuwentao) ([41c9f32](https://github.com/wuwentao/midea-lan/commit/41c9f327e4d5e11fa4e20b67a649750cd8ca0c95))
- **c3:** Parse x00 sensor telemetry for c3 17100007  model [#211](https://github.com/wuwentao/midea-lan/pull/211) by [@wuwentao](https://github.com/wuwentao) ([192d86c](https://github.com/wuwentao/midea-lan/commit/192d86c44d34570bd61c1ea02bdcf48c4f954d7e))
- **discover:** Parse plaintext LAN broadcasts from newer devices [#220](https://github.com/wuwentao/midea-lan/pull/220) by [@wuwentao](https://github.com/wuwentao) ([f111d56](https://github.com/wuwentao/midea-lan/commit/f111d5612d836c94db709022709851fbc87ab5ea))
- **c3:** Support 171000AU short protocol [#199](https://github.com/wuwentao/midea-lan/pull/199) by [@wuwentao](https://github.com/wuwentao) ([dd14b53](https://github.com/wuwentao/midea-lan/commit/dd14b538f3be9e1d2454c1b0199b146283493f1b))
- **ac:** Use advertised outdoor silent value [#228](https://github.com/wuwentao/midea-lan/pull/228) by [@wuwentao](https://github.com/wuwentao) ([f9b8c82](https://github.com/wuwentao/midea-lan/commit/f9b8c82d9632d28c9293dc6bb577b12b6f410903))
- **fa:** Support model 56011C99 swing control via CB4 frame [#221](https://github.com/wuwentao/midea-lan/pull/221) by [@wuwentao](https://github.com/wuwentao) ([e036569](https://github.com/wuwentao/midea-lan/commit/e0365697c12f5e825dce3fa43583b214f087db62))
- **fa:** Support BGF10000 preset submodes [#226](https://github.com/wuwentao/midea-lan/pull/226) by [@lc5900](https://github.com/lc5900) ([b516fa2](https://github.com/wuwentao/midea-lan/commit/b516fa2b53ab756edb9e4743b8d523af16fcc626))

### Documentation
- Rename leftover "Midea local" docstrings to "Midea lan" [#177](https://github.com/wuwentao/midea-lan/pull/177) by [@wuwentao](https://github.com/wuwentao) ([fd76785](https://github.com/wuwentao/midea-lan/commit/fd76785f40eda3f5a0db3238466ea581692d8f08))
- Add new-device support guide (en/zh-Hans) [#180](https://github.com/wuwentao/midea-lan/pull/180) by [@wuwentao](https://github.com/wuwentao) ([40d8cbc](https://github.com/wuwentao/midea-lan/commit/40d8cbc06b9d48530c6c46235a7f39ccbee6c9e3))

### Testing
- **tsmartlife:** Cover download_lua/download_plugin inheritance from SmartHomeCloud [#215](https://github.com/wuwentao/midea-lan/pull/215) by [@jaspweowaale](https://github.com/jaspweowaale) ([db79046](https://github.com/wuwentao/midea-lan/commit/db7904687693541e1e8f6ae9df7ee0310cd0485a))

### Miscellaneous Tasks
- Add CodeRabbit configuration [#178](https://github.com/wuwentao/midea-lan/pull/178) by [@wuwentao](https://github.com/wuwentao) ([43bdf1f](https://github.com/wuwentao/midea-lan/commit/43bdf1f24189f7d26dcb799e792ce4b223d345b8))
- Add funding links [#210](https://github.com/wuwentao/midea-lan/pull/210) by [@wuwentao](https://github.com/wuwentao) ([4359f66](https://github.com/wuwentao/midea-lan/commit/4359f6628dd9a3f5cf14287d1b4efbfd50150835))
- **ac:** Add b5 capability tags [#172](https://github.com/wuwentao/midea-lan/pull/172) by [@wuwentao](https://github.com/wuwentao) ([d668628](https://github.com/wuwentao/midea-lan/commit/d6686280ee33094978137e8ed145cf74bdcede4e))
## [2026.9.2](https://github.com/wuwentao/midea-lan/compare/v2026.9.1...v2026.9.2) (2026-09-24)

### Features
- **b1:** Expose oven programme number and target temperature [#102](https://github.com/wuwentao/midea-lan/pull/102) by [@ZeuSJke](https://github.com/ZeuSJke) ([f501fd7](https://github.com/wuwentao/midea-lan/commit/f501fd7ecd76ba8373153d7d417b556635570b55))
- **c3:** Add human-readable error_code_description [#80](https://github.com/wuwentao/midea-lan/pull/80) by [@vasicekmilan90-eng](https://github.com/vasicekmilan90-eng) ([c4f7086](https://github.com/wuwentao/midea-lan/commit/c4f7086bb71f28b07904a7540e74504edfcfdd29))
- **c3:** Parse ASCII tail identifier and firmware versions [#81](https://github.com/wuwentao/midea-lan/pull/81) by [@vasicekmilan90-eng](https://github.com/vasicekmilan90-eng) ([e3968ea](https://github.com/wuwentao/midea-lan/commit/e3968eaaa913cb77bf700a00b4a17a2b9c3b2e2f))
- **c3:** Expose compressor total run time from X05 notify [#82](https://github.com/wuwentao/midea-lan/pull/82) by [@vasicekmilan90-eng](https://github.com/vasicekmilan90-eng) ([3099c5c](https://github.com/wuwentao/midea-lan/commit/3099c5c1fe951f061cf1ff5e429ffecb23441244))
- **c3:** Decode reg 129 load output bitmap [#83](https://github.com/wuwentao/midea-lan/pull/83) by [@vasicekmilan90-eng](https://github.com/vasicekmilan90-eng) ([6d4827e](https://github.com/wuwentao/midea-lan/commit/6d4827e5a9858ed0e9acf4ae5b50a836a3315791))
- **e3:** Add cloud usage report API and client [#107](https://github.com/wuwentao/midea-lan/pull/107) by [@skyel1u](https://github.com/skyel1u) ([df98864](https://github.com/wuwentao/midea-lan/commit/df98864fef0edfc0c1452b02160cfde3ca780cb4))
- **c1:** Add support for Midea C1 device [#117](https://github.com/wuwentao/midea-lan/pull/117) by [@yurkiv](https://github.com/yurkiv) ([40aa07b](https://github.com/wuwentao/midea-lan/commit/40aa07bb59a8a1f816a7ce8a62d8a1cf69a7a1fb))
- **c3:** Wire remaining PR#46 attributes, add compressor_on/dc_bus_voltage, map probe sentinels [#123](https://github.com/wuwentao/midea-lan/pull/123) by [@vasicekmilan90-eng](https://github.com/vasicekmilan90-eng) ([aa4b1a5](https://github.com/wuwentao/midea-lan/commit/aa4b1a5cf8315a09c1a02063fa45f055f380fe9e))
- **ac:** Add degerming state and control [#124](https://github.com/wuwentao/midea-lan/pull/124) by [@jazzzzmaybe](https://github.com/jazzzzmaybe) ([af5ef15](https://github.com/wuwentao/midea-lan/commit/af5ef15b86975a6e152036a1865dd032504aef4e))
- **b8:** Expose work status control [#128](https://github.com/wuwentao/midea-lan/pull/128) by [@wuwentao](https://github.com/wuwentao) ([adb204d](https://github.com/wuwentao/midea-lan/commit/adb204d561220315b1ccc92f2c169727562e5b33))
- **b8:** Expose control option lists [#132](https://github.com/wuwentao/midea-lan/pull/132) by [@wuwentao](https://github.com/wuwentao) ([e9199dc](https://github.com/wuwentao/midea-lan/commit/e9199dc6e2cc91e4aec6e7bb8f36d178be2cb3ea))
- **ac:** Add light sensitivity, timer and self-clean states; make two tags queryable [#134](https://github.com/wuwentao/midea-lan/pull/134) by [@jazzzzmaybe](https://github.com/jazzzzmaybe) ([f56041e](https://github.com/wuwentao/midea-lan/commit/f56041e8c747156f5bdb9699ef0c36d775c492fa))
- **ed:** Expand water purifier status and controls [#136](https://github.com/wuwentao/midea-lan/pull/136) by [@jazzzzmaybe](https://github.com/jazzzzmaybe) ([0dac92f](https://github.com/wuwentao/midea-lan/commit/0dac92fcc9afad0c449d5693a9719c2ac03fc3b0))
- **fa:** Support legacy and protocol v5 FA devices [#13](https://github.com/wuwentao/midea-lan/pull/13) by [@wuwentao](https://github.com/wuwentao) ([f9112d9](https://github.com/wuwentao/midea-lan/commit/f9112d927c5fe0d4ec296c2814a92f4f0032cdda))

### Bug Fixes
- Use PAT to create release so PyPI deploy is triggered [#101](https://github.com/wuwentao/midea-lan/pull/101) by [@wuwentao](https://github.com/wuwentao) ([e46454e](https://github.com/wuwentao/midea-lan/commit/e46454eae78585ec61917ce3c1503a81a6f795de))
- **cd:** Add known model to new protocol list [#106](https://github.com/wuwentao/midea-lan/pull/106) by [@wuwentao](https://github.com/wuwentao) ([dc9d93c](https://github.com/wuwentao/midea-lan/commit/dc9d93cd352ade1b459180b3dffc83e5d064a669))
- Resolve CodeRabbit security and correctness issues [#110](https://github.com/wuwentao/midea-lan/pull/110) by [@wuwentao](https://github.com/wuwentao) ([c90dd9a](https://github.com/wuwentao/midea-lan/commit/c90dd9a21c8b0e0176bc519675c179753cf0075d))
- **device:** Run init probes after appliance query timeout [#120](https://github.com/wuwentao/midea-lan/pull/120) by [@wuwentao](https://github.com/wuwentao) ([cc1106f](https://github.com/wuwentao/midea-lan/commit/cc1106f9b10aacd8455b3c7aa4486f5925ce4b45))
- **ac:** Fix a0/c0 message min len check [#119](https://github.com/wuwentao/midea-lan/pull/119) by [@wuwentao](https://github.com/wuwentao) ([1d5e40d](https://github.com/wuwentao/midea-lan/commit/1d5e40dc9af900a6347f616efa68fe1b0a1725be))
- **ac:** Decode C0 temperatures for model 220F4047 [#60](https://github.com/wuwentao/midea-lan/pull/60) by [@yezhiming1](https://github.com/yezhiming1) ([06d4d34](https://github.com/wuwentao/midea-lan/commit/06d4d3456f2dabf5c2f54577ace8fc5ce71240ae))
- **ac:** Split B1 properties queries into independent batches [#111](https://github.com/wuwentao/midea-lan/pull/111) by [@wuwentao](https://github.com/wuwentao) ([e73222f](https://github.com/wuwentao/midea-lan/commit/e73222f595b5d40f5d593c7a33ab2024d64441d4))
- **ac:** Encode low target temperatures [#121](https://github.com/wuwentao/midea-lan/pull/121) by [@wuwentao](https://github.com/wuwentao) ([4f6559b](https://github.com/wuwentao/midea-lan/commit/4f6559b8fd0c943264b7723ae6c158b9b3ce3f78))
- **b8:** Align vacuum protocol controls [#126](https://github.com/wuwentao/midea-lan/pull/126) by [@wuwentao](https://github.com/wuwentao) ([4bf46e2](https://github.com/wuwentao/midea-lan/commit/4bf46e22fd24c1ceba4009fffc86ea0e6f42ef59))
- **b8:** Reject invalid numeric controls [#129](https://github.com/wuwentao/midea-lan/pull/129) by [@wuwentao](https://github.com/wuwentao) ([34bfdff](https://github.com/wuwentao/midea-lan/commit/34bfdffbc0d74a8e2a0bdc0958f7901910dcffb7))
- **b8:** Use protocol defaults before first status [#130](https://github.com/wuwentao/midea-lan/pull/130) by [@wuwentao](https://github.com/wuwentao) ([bde01f1](https://github.com/wuwentao/midea-lan/commit/bde01f10aa546910287fb771330f5c4793516db9))
- **ac:** Cap capability query batches at 9 properties [#127](https://github.com/wuwentao/midea-lan/pull/127) by [@jazzzzmaybe](https://github.com/jazzzzmaybe) ([be7c52c](https://github.com/wuwentao/midea-lan/commit/be7c52c58769c276b8fd3deb7d9afb578dd2cdc5))
- **cd:** Normalize preset value separators [#165](https://github.com/wuwentao/midea-lan/pull/165) by [@wuwentao](https://github.com/wuwentao) ([51077b8](https://github.com/wuwentao/midea-lan/commit/51077b8bb818d2e344064d234c9ab86fd947db80))
- **db:** Normalize progress value separators [#166](https://github.com/wuwentao/midea-lan/pull/166) by [@wuwentao](https://github.com/wuwentao) ([105a391](https://github.com/wuwentao/midea-lan/commit/105a391604b0daff24c0ff0d189cc861b5a17ebb))
- **fa:** Normalize swing value separators [#162](https://github.com/wuwentao/midea-lan/pull/162) by [@wuwentao](https://github.com/wuwentao) ([e884e87](https://github.com/wuwentao/midea-lan/commit/e884e87b9aac2cce698035a46b89e06b2ec3379f))
- **ac:** Normalize swing value separators [#164](https://github.com/wuwentao/midea-lan/pull/164) by [@wuwentao](https://github.com/wuwentao) ([5830440](https://github.com/wuwentao/midea-lan/commit/58304404670d8fd23b098426d92ad4c8d2290890))
- **e1:** Normalize progress value separators [#163](https://github.com/wuwentao/midea-lan/pull/163) by [@wuwentao](https://github.com/wuwentao) ([946866a](https://github.com/wuwentao/midea-lan/commit/946866a0a1aba85b076577e44b8bea42396621e8))
- **a1:** Normalize mode value separators [#167](https://github.com/wuwentao/midea-lan/pull/167) by [@wuwentao](https://github.com/wuwentao) ([1dbbf37](https://github.com/wuwentao/midea-lan/commit/1dbbf3768af370a406df69c6574728b744daa585))

### Refactor
- Remove redundant .release-please-manifest.json and add security fixes [#105](https://github.com/wuwentao/midea-lan/pull/105) by [@wuwentao](https://github.com/wuwentao) ([2eb2bac](https://github.com/wuwentao/midea-lan/commit/2eb2baceca58daf57518f08e9dc3a76214e5d970))
- **b8:** Keep protocol values raw in messages [#133](https://github.com/wuwentao/midea-lan/pull/133) by [@wuwentao](https://github.com/wuwentao) ([0b67ad9](https://github.com/wuwentao/midea-lan/commit/0b67ad979777d9799170c8dfb45281f7164eb020))
- **a1:** Lowercase device values [#138](https://github.com/wuwentao/midea-lan/pull/138) by [@wuwentao](https://github.com/wuwentao) ([54904b8](https://github.com/wuwentao/midea-lan/commit/54904b8cca8c4157ac1270d88694cdbfae1d3194))
- **b0:** Lowercase device values [#139](https://github.com/wuwentao/midea-lan/pull/139) by [@wuwentao](https://github.com/wuwentao) ([b0caf42](https://github.com/wuwentao/midea-lan/commit/b0caf42dbad5896d7cdaf3e59aa49460ad6f7e25))
- **b1:** Lowercase device values [#140](https://github.com/wuwentao/midea-lan/pull/140) by [@wuwentao](https://github.com/wuwentao) ([6daf868](https://github.com/wuwentao/midea-lan/commit/6daf86830ff64a2c9c245e2a27393de2f1e74e0e))
- **b3:** Lowercase device values [#141](https://github.com/wuwentao/midea-lan/pull/141) by [@wuwentao](https://github.com/wuwentao) ([026d1ca](https://github.com/wuwentao/midea-lan/commit/026d1caead672ce66923b82649afa75fccb4dbec))
- **b4:** Lowercase device values [#142](https://github.com/wuwentao/midea-lan/pull/142) by [@wuwentao](https://github.com/wuwentao) ([1b896d4](https://github.com/wuwentao/midea-lan/commit/1b896d4dfbf217a3296dbfe79ca80c57615380c9))
- **b6:** Lowercase device values [#143](https://github.com/wuwentao/midea-lan/pull/143) by [@wuwentao](https://github.com/wuwentao) ([ebe16a9](https://github.com/wuwentao/midea-lan/commit/ebe16a9a4b7aa95846ad8c772b60a4a64388bc01))
- **c3:** Lowercase device values [#144](https://github.com/wuwentao/midea-lan/pull/144) by [@wuwentao](https://github.com/wuwentao) ([cf88f73](https://github.com/wuwentao/midea-lan/commit/cf88f735d73be9d56efd64db98eb9d01aacd729c))
- **cc:** Lowercase device values [#145](https://github.com/wuwentao/midea-lan/pull/145) by [@wuwentao](https://github.com/wuwentao) ([a3da01a](https://github.com/wuwentao/midea-lan/commit/a3da01abf353278c777a1d295b9135387147ceab))
- **cd:** Lowercase device values [#146](https://github.com/wuwentao/midea-lan/pull/146) by [@wuwentao](https://github.com/wuwentao) ([9fbd639](https://github.com/wuwentao/midea-lan/commit/9fbd63928bda1869d5a00b1f2a020652c13c97af))
- **ce:** Lowercase device values [#147](https://github.com/wuwentao/midea-lan/pull/147) by [@wuwentao](https://github.com/wuwentao) ([ec207d3](https://github.com/wuwentao/midea-lan/commit/ec207d3924c70ab3c3e255cf046fe1ac1a42afd1))
- **da:** Lowercase device values [#148](https://github.com/wuwentao/midea-lan/pull/148) by [@wuwentao](https://github.com/wuwentao) ([e325f2e](https://github.com/wuwentao/midea-lan/commit/e325f2e9d3b56ec29057c31ade500a35e4204b14))
- **db:** Lowercase device values [#149](https://github.com/wuwentao/midea-lan/pull/149) by [@wuwentao](https://github.com/wuwentao) ([75588a9](https://github.com/wuwentao/midea-lan/commit/75588a9ab1dd18bcd39671afc8f07a382c42dd85))
- **dc:** Lowercase device values [#150](https://github.com/wuwentao/midea-lan/pull/150) by [@wuwentao](https://github.com/wuwentao) ([1a098a2](https://github.com/wuwentao/midea-lan/commit/1a098a2c590efdd704978c5e72b3af34448de712))
- **e1:** Lowercase device values [#151](https://github.com/wuwentao/midea-lan/pull/151) by [@wuwentao](https://github.com/wuwentao) ([d4cc487](https://github.com/wuwentao/midea-lan/commit/d4cc48748be9d6b542e2c5413f6f142f9470bf20))
- **x13:** Lowercase device values [#158](https://github.com/wuwentao/midea-lan/pull/158) by [@wuwentao](https://github.com/wuwentao) ([93b7ff8](https://github.com/wuwentao/midea-lan/commit/93b7ff8a89c9a70d8e4e205bbb0ccebb70042848))
- **x40:** Lowercase device values [#161](https://github.com/wuwentao/midea-lan/pull/161) by [@wuwentao](https://github.com/wuwentao) ([2e68510](https://github.com/wuwentao/midea-lan/commit/2e68510002062c887160bd9f33254e14c479ce65))
- **x34:** Lowercase device values [#160](https://github.com/wuwentao/midea-lan/pull/160) by [@wuwentao](https://github.com/wuwentao) ([1ef039d](https://github.com/wuwentao/midea-lan/commit/1ef039d3292e121b9b310543720b6babe024ff57))
- **fd:** Lowercase device values [#157](https://github.com/wuwentao/midea-lan/pull/157) by [@wuwentao](https://github.com/wuwentao) ([da58cf1](https://github.com/wuwentao/midea-lan/commit/da58cf1560fab34ef084d6aa70a27cfc1938dc02))
- **fb:** Lowercase device values [#155](https://github.com/wuwentao/midea-lan/pull/155) by [@wuwentao](https://github.com/wuwentao) ([3db9553](https://github.com/wuwentao/midea-lan/commit/3db955373e4015701175373282b09bc2fccbe80b))
- **ec:** Lowercase device values [#154](https://github.com/wuwentao/midea-lan/pull/154) by [@wuwentao](https://github.com/wuwentao) ([cfacadd](https://github.com/wuwentao/midea-lan/commit/cfacaddc3eb6e0e0504a5f1c10915bf866a190e5))
- **ea:** Lowercase device values [#153](https://github.com/wuwentao/midea-lan/pull/153) by [@wuwentao](https://github.com/wuwentao) ([59a9ca9](https://github.com/wuwentao/midea-lan/commit/59a9ca99fd9720f9f4e43a056bb74ed0910dc60c))
- **e8:** Lowercase device values [#152](https://github.com/wuwentao/midea-lan/pull/152) by [@wuwentao](https://github.com/wuwentao) ([a4d1aab](https://github.com/wuwentao/midea-lan/commit/a4d1aab7d8a8f786b23cc78fbb64588b4664dfd8))
- **x26:** Lowercase device values [#159](https://github.com/wuwentao/midea-lan/pull/159) by [@wuwentao](https://github.com/wuwentao) ([83d059a](https://github.com/wuwentao/midea-lan/commit/83d059ad2c9ca4957554d01e753716a943137ff5))
- **fc:** Lowercase device values [#156](https://github.com/wuwentao/midea-lan/pull/156) by [@wuwentao](https://github.com/wuwentao) ([c671621](https://github.com/wuwentao/midea-lan/commit/c671621478e2ee5a670bd16a403361d6be372f1f))
## [2026.9.1](https://github.com/wuwentao/midea-lan/compare/v2026.9.0...v2026.9.1) (2026-09-08)

### Features

- **ac:** Add HA integration support properties [#92](https://github.com/wuwentao/midea-lan/pull/92) by [@wuwentao](https://github.com/wuwentao) ([6274cd7](https://github.com/wuwentao/midea-lan/commit/6274cd79177d72f68d52c4884fb458a52c8d117a))

- Add manual release workflow with git-cliff [#94](https://github.com/wuwentao/midea-lan/pull/94) by [@wuwentao](https://github.com/wuwentao) ([045b9ef](https://github.com/wuwentao/midea-lan/commit/045b9efea8c354a38100294eca1b6ac1988e1bb7))


### Bug Fixes

- **ci:** Add push trigger to release-please workflow [#78](https://github.com/wuwentao/midea-lan/pull/78) by [@wuwentao](https://github.com/wuwentao) ([12fd765](https://github.com/wuwentao/midea-lan/commit/12fd7652c91d9152a5dad2f806d0a7b737d3524c))

- Remove non-existent release label from PR creation [#96](https://github.com/wuwentao/midea-lan/pull/96) by [@wuwentao](https://github.com/wuwentao) ([e96ddb5](https://github.com/wuwentao/midea-lan/commit/e96ddb5ffc4293aac71b52eacfd6c34ea471351b))

- Handle stale branch and existing PR in manual-release workflow [#97](https://github.com/wuwentao/midea-lan/pull/97) by [@wuwentao](https://github.com/wuwentao) ([d686d25](https://github.com/wuwentao/midea-lan/commit/d686d258b3fe042731209e7075b8b9e44014bfa4))

- Generate prettier-compatible manifest json format [#99](https://github.com/wuwentao/midea-lan/pull/99) by [@wuwentao](https://github.com/wuwentao) ([c4466a3](https://github.com/wuwentao/midea-lan/commit/c4466a3136fa8d44fc088f43d242c56b5114b255))


### Refactor

- **ac:** Improve PropertiesQuery tag categorization and add ieco support [#86](https://github.com/wuwentao/midea-lan/pull/86) by [@wuwentao](https://github.com/wuwentao) ([d265568](https://github.com/wuwentao/midea-lan/commit/d265568d567cd374b7ff33a94068a55bc8a59c34))

- **ac:** Store B5 temperature limits in capabilities map [#87](https://github.com/wuwentao/midea-lan/pull/87) by [@wuwentao](https://github.com/wuwentao) ([ad6272d](https://github.com/wuwentao/midea-lan/commit/ad6272dc4b6669203fd216f9f188fc852bda4767))

- **ac:** Nest B5 mode flags into capabilities modes map [#88](https://github.com/wuwentao/midea-lan/pull/88) by [@wuwentao](https://github.com/wuwentao) ([b16efb8](https://github.com/wuwentao/midea-lan/commit/b16efb8341827c7831502ee343c06c37ce7e5dd5))

- **ac:** Unify capabilities format to arrays [#91](https://github.com/wuwentao/midea-lan/pull/91) by [@wuwentao](https://github.com/wuwentao) ([ca0d21a](https://github.com/wuwentao/midea-lan/commit/ca0d21a7903491e785daf82d3da1f889787279e4))

# Changelog

## [2026.9.0](https://github.com/wuwentao/midea-lan/compare/v2026.8.0...v2026.9.0) (2026-09-02)


### ⚠ BREAKING CHANGES

* **ac:** removes NewProtocolSelfCleanQuery subclass

### Features

* **ac:** run B5 capability queries once and publish results to HA ([#63](https://github.com/wuwentao/midea-lan/issues/63)) by [@wuwentao](https://github.com/wuwentao) ([874e3fd](https://github.com/wuwentao/midea-lan/commit/874e3fdc74153f5d4f5617ad6c9aa95331ccce49))
* **ac:** support iECO query and set ([#70](https://github.com/wuwentao/midea-lan/issues/70)) by [@wuwentao](https://github.com/wuwentao) ([89d7dfe](https://github.com/wuwentao/midea-lan/commit/89d7dfea6c9c6e732a0a31163539979f7918b24c))
* **bf:** implement full BF microwave steam oven message parsing and … ([#23](https://github.com/wuwentao/midea-lan/issues/23)) by [@billhu1996](https://github.com/billhu1996) ([a8d918f](https://github.com/wuwentao/midea-lan/commit/a8d918f1c4e34a1e7e4e9e85e5296eb25f2a2d7c))
* **c3:** expose outdoor-unit runtime telemetry as device attributes ([#53](https://github.com/wuwentao/midea-lan/issues/53)) by [@kmich](https://github.com/kmich) ([4b91c8f](https://github.com/wuwentao/midea-lan/commit/4b91c8f44cb7e3ed4d4af180e7ddf411c8bec8f1))
* **c3:** expose outdoor-unit telemetry as device attributes ([#58](https://github.com/wuwentao/midea-lan/issues/58)) by [@kmich](https://github.com/kmich) ([b25433b](https://github.com/wuwentao/midea-lan/commit/b25433b41a24d60115ebc0473ca73acf88d5f920))
* **c3:** parse the MSG_TYPE_UP_UNITPARA notify ([#55](https://github.com/wuwentao/midea-lan/issues/55)) by [@kmich](https://github.com/kmich) ([85940db](https://github.com/wuwentao/midea-lan/commit/85940dbfb7aba61d179a2e2a7c39577366a2ca44))
* **cd:** support extended water heater protocol ([#61](https://github.com/wuwentao/midea-lan/issues/61)) by [@FrancYescO](https://github.com/FrancYescO) ([e2a6fd2](https://github.com/wuwentao/midea-lan/commit/e2a6fd2ae31ce41e5f3275229d8858d00039d0b3))


### Bug Fixes

* **ac:** correct rate_select gears and set path for reported levels ([#65](https://github.com/wuwentao/midea-lan/issues/65)) by [@wuwentao](https://github.com/wuwentao) ([38c4ed0](https://github.com/wuwentao/midea-lan/commit/38c4ed0a6ec47d7238813a2f86fecaada11984d9))
* **ac:** guard XA1Body parsing against short notify bodies ([#42](https://github.com/wuwentao/midea-lan/issues/42)) by [@tompsonpecini](https://github.com/tompsonpecini) ([460063f](https://github.com/wuwentao/midea-lan/commit/460063fc8eb4c231dc837446b12fdec2b12cc7fd))
* **ac:** keep unit on when a mode change is followed by a temperature write ([#12](https://github.com/wuwentao/midea-lan/issues/12)) by [@wuwentao](https://github.com/wuwentao) ([27ddba1](https://github.com/wuwentao/midea-lan/commit/27ddba1b00c6681fddc7e605e8f3e50b2454e78d)), closes [#495](https://github.com/wuwentao/midea-lan/issues/495)
* **ac:** remove error_code_query from default list ([#64](https://github.com/wuwentao/midea-lan/issues/64)) by [@wuwentao](https://github.com/wuwentao) ([ba48fb9](https://github.com/wuwentao/midea-lan/commit/ba48fb96524fe37ab6acf125fc1d6fe1ee958474))
* **b0:** correct status labels 0x02/0x03 on subtype zero ([#14](https://github.com/wuwentao/midea-lan/issues/14)) by [@matvejalekseev](https://github.com/matvejalekseev) ([a0bf866](https://github.com/wuwentao/midea-lan/commit/a0bf866b6ba39c7d17b1ae5b8cee491fe78f026d))
* **c3:** align four X10 UnitPara offsets with the official lua protocol ([#52](https://github.com/wuwentao/midea-lan/issues/52)) by [@kmich](https://github.com/kmich) ([aeee249](https://github.com/wuwentao/midea-lan/commit/aeee249dc3abf17bc8455ce30ce40fd61f69e784))
* **c3:** correct outdoor fan speed parsing and add regression coverage ([#51](https://github.com/wuwentao/midea-lan/issues/51)) by [@kmich](https://github.com/kmich) ([e4a8e34](https://github.com/wuwentao/midea-lan/commit/e4a8e345d11a52020dae7c2bec6594c37f4815a5))
* **c3:** shift 32-bit energy counters by 24, not 32 ([#54](https://github.com/wuwentao/midea-lan/issues/54)) by [@kmich](https://github.com/kmich) ([2008d17](https://github.com/wuwentao/midea-lan/commit/2008d1710e9be9b530fcccff1206d1110132d4f3))
* **cd:** don't let SET echo clobber power state ([#11](https://github.com/wuwentao/midea-lan/issues/11)) by [@wuwentao](https://github.com/wuwentao) ([95fe914](https://github.com/wuwentao/midea-lan/commit/95fe914bde5e76bc0b3f2862ea311ccabd8877f8))
* close socket catch error ([#28](https://github.com/wuwentao/midea-lan/issues/28)) by [@wuwentao](https://github.com/wuwentao) ([f72c482](https://github.com/wuwentao/midea-lan/commit/f72c48215a52cb598908465a60cf041cbd23cf3c))
* **cloud:** support legacy lua download for MideaAirCloud ([#10](https://github.com/wuwentao/midea-lan/issues/10)) by [@wuwentao](https://github.com/wuwentao) ([f47c3a0](https://github.com/wuwentao/midea-lan/commit/f47c3a0d8bbfa873e04fb5d6d6b62a676fb395f8))
* **cloud:** use the v2 getToken endpoint for the Meiju cloud ([#44](https://github.com/wuwentao/midea-lan/issues/44)) by [@wawnnzxd](https://github.com/wawnnzxd) ([67f1eda](https://github.com/wuwentao/midea-lan/commit/67f1eda757fad4a4a4fd6e8457ee8de87452578b))
* **device:** recover from a device that supports no query protocol ([#41](https://github.com/wuwentao/midea-lan/issues/41)) by [@ajplotkin](https://github.com/ajplotkin) ([b38e556](https://github.com/wuwentao/midea-lan/commit/b38e556bb1b513cfeb06f4654cb934ba1007c540))
* **e2:** make precision_halves symmetric so target temperature round-trips ([#19](https://github.com/wuwentao/midea-lan/issues/19)) by [@edihasaj](https://github.com/edihasaj) ([f801dca](https://github.com/wuwentao/midea-lan/commit/f801dcaf0d17007ad527bfc07c96b84e43a9fd52))
* **e2:** warn and ignore old-protocol attributes MessageSet cannot carry ([#17](https://github.com/wuwentao/midea-lan/issues/17)) by [@edihasaj](https://github.com/edihasaj) ([6f351c9](https://github.com/wuwentao/midea-lan/commit/6f351c961b5328dd7dfc894931e6868c6d55e6c8))
* **ed:** cancel queued tea bar heating after filling ([#5](https://github.com/wuwentao/midea-lan/issues/5)) by [@xiaopan007](https://github.com/xiaopan007) ([2b8bec7](https://github.com/wuwentao/midea-lan/commit/2b8bec7baf1c3e1b66aa2589cb6436d892eb688b))
* **fa:** support extended fan modes ([#50](https://github.com/wuwentao/midea-lan/issues/50)) by [@Nosuchipsu](https://github.com/Nosuchipsu) ([7df6292](https://github.com/wuwentao/midea-lan/commit/7df62922fd8621e5f45877a7f802a57634725b70))


### Documentation

* document cloud download CLI ([#22](https://github.com/wuwentao/midea-lan/issues/22)) by [@wuwentao](https://github.com/wuwentao) ([75f1450](https://github.com/wuwentao/midea-lan/commit/75f1450c80df36840b34090307cbc4798aa2eee6))


### Miscellaneous Chores

* release 2026.9.0 ([#76](https://github.com/wuwentao/midea-lan/issues/76)) by [@wuwentao](https://github.com/wuwentao) ([370a717](https://github.com/wuwentao/midea-lan/commit/370a717520273891c0fa22f939cc808885f3e425))


### Code Refactoring

* **ac:** merge NewProtocolQuery and add customize capabilities override ([#66](https://github.com/wuwentao/midea-lan/issues/66)) by [@wuwentao](https://github.com/wuwentao) ([74ff962](https://github.com/wuwentao/midea-lan/commit/74ff9628bd52161145d49d5ae115f6479f25bbde))

## [2026.8.0](https://github.com/wuwentao/midea-lan/compare/midea-lan-v2026.7.0...midea-lan-v2026.8.0) (2026-08-12)


### Features

* **ac:** gate rate_select query behind b5_electricity capability ([#632](https://github.com/wuwentao/midea-lan/issues/632)) by [@vaughnitem](https://github.com/vaughnitem) ([30bd23b](https://github.com/wuwentao/midea-lan/commit/30bd23bdf427b5fe109d567011d3825f1d046044))
* **b1:** decode X01 fallback query responses ([#633](https://github.com/wuwentao/midea-lan/issues/633)) by [@matvejalekseev](https://github.com/matvejalekseev) ([659aa2a](https://github.com/wuwentao/midea-lan/commit/659aa2adc4e647d0059fc801e2bbf24d2663c2a8))
* **ed:** support subtype 395 tea bar appliances ([#628](https://github.com/wuwentao/midea-lan/issues/628)) by [@xiaopan007](https://github.com/xiaopan007) ([b4c811b](https://github.com/wuwentao/midea-lan/commit/b4c811b812de0ee49fe65a5fae83367ce26de741))
* midea-lan init commit by [@wuwentao](https://github.com/wuwentao) ([6ae208d](https://github.com/wuwentao/midea-lan/commit/6ae208de7b755e41d9feb249c4d7f9fabb9c87b0))


### Bug Fixes

* **b0:** ignore 31 body on subtype zero devices ([#629](https://github.com/wuwentao/midea-lan/issues/629)) by [@matvejalekseev](https://github.com/matvejalekseev) ([569cc83](https://github.com/wuwentao/midea-lan/commit/569cc83d8fcc94861ee3931af34e1d538e146195))

## Changelog
