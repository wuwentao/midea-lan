## Summary

<!-- What changed, and why? Include the affected device type/model when relevant. -->

## Related issues and pull requests

- `midea-lan` issue: <!-- Link, or N/A with a short reason. -->
- [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) issue: <!-- Link the related issue, or N/A with a short reason. -->
- Matching [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) PR: <!-- Link, or N/A if this change cannot affect the integration. -->

<!--
For changes that affect Home Assistant behavior or device support, open the
midea_ac_lan PR at the same time and link it back to this PR. Do not update the
midea-lan version in midea_ac_lan/custom_components/midea_ac_lan/manifest.json.
Maintainers will update that dependency centrally after a midea-lan release.
-->

## Protocol source

- Lua protocol file(s) or source: <!-- Link to the exact file(s) in https://github.com/wuwentao/midea-lua. -->
- [`midea-lua`](https://github.com/wuwentao/midea-lua) PR: <!-- Link when the required Lua was not already present; otherwise N/A. -->

<!--
When a device protocol applies, the PR should identify its exact Lua source. If
the Lua is not yet in https://github.com/wuwentao/midea-lua, follow that
repository's README to download it and submit it there first, then link that PR
above. If no Lua protocol applies, use N/A and explain why.
-->

## Tests and verification

- Commands run:
- Hardware/device verification:
- Codecov patch coverage: <!-- Must be 100% for added or changed executable code. -->

## Checklist

<!--
After the PR is open and CodeRabbit finishes its review, address every actionable
comment, reply with the fix and test evidence, and resolve each conversation
before merge.
-->

- [ ] I linked the device Lua protocol in [`midea-lua`](https://github.com/wuwentao/midea-lua), or explained why no protocol source applies.
- [ ] I linked the related [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) issue, or explained why none applies.
- [ ] I opened and linked the matching [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) PR, or explained why none applies.

## Release note

Merging this PR does not trigger an immediate release. Maintainers accumulate a
set of merged PRs, publish `midea-lan` manually on a periodic basis, and then
update/synchronize `midea_ac_lan` centrally.
