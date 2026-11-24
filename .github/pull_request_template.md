## Summary

<!-- What changed, and why? Include the affected device type/model when relevant. -->

## Related issues and pull requests

- `midea-lan` issue: <!-- Link, or N/A with a short reason. -->
- [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) issue: <!-- Link the related issue, or N/A with a short reason. -->
- Matching [`midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) PR: <!-- Link, or N/A if this change cannot affect the integration. -->

<!--
For changes that affect Home Assistant behavior or device support, open the
midea_ac_lan integration PR at the same time and link it back to this lib PR.
While this library PR is unmerged, that integration PR may point the midea-lan
requirement in manifest.json at this fork/branch so its feature and CI can be verified. The integration manifest is
the sole runtime dependency source; its CI and local setup install from it.
`pyproject.toml` and `uv.lock` in the integration repository contain only
development/test dependencies and must not include this library. After this lib
PR merges, the integration PR must switch its manifest to
"midea-lan@git+https://github.com/wuwentao/midea-lan.git@main" unless it already
uses upstream main. It may merge only when the manifest references upstream main
or a released midea-lan version; it must not retain a contributor fork/branch.
Library PR merge does not trigger an immediate release, and the integration PR
does not need to wait for one. Maintainers periodically publish midea-lan and
then midea_ac_lan based on merged PRs, generating the changelog and updating the
integration manifest to the released library version containing the merged changes.
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

Merging this PR does not trigger an immediate library release. The matching
`midea_ac_lan` PR can validate against this fork/branch before merge and upstream
`main` afterward, so it does not need to wait for a release. Maintainers
periodically publish `midea-lan`; when publishing the integration, they first
confirm a released library version contains the merged changes, then replace
its upstream-main requirement with that version.
