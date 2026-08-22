## Related issue

Closes or relates to:

## Change type

- [ ] Bug fix
- [ ] Feature
- [ ] Kernel or UAPI contract
- [ ] Scenario or report schema
- [ ] Documentation or maintenance

## Why

Describe the problem and the observable behavior this change should provide.

## What changed

-

## Design and alternatives

Explain non-obvious choices, rejected alternatives, and compatibility effects.

## Compatibility

- [ ] No user-visible compatibility change
- [ ] Backward-compatible behavior or document field added
- [ ] Breaking UAPI, CLI, scenario, or report change with version/migration notes

## Verification

List the exact commands, environment, and results. Attach relevant terminal or
kernel log excerpts when the change affects the kernel module.

- [ ] Normal path tested
- [ ] Invalid input or failure path tested
- [ ] Repeated execution tested
- [ ] Kernel warning/oops checked, when applicable
- [ ] Cleanup leaves no module, device node, monitor process, or active fault

Environment and exact commands:

```text
OS:
Kernel:
Compiler:
Python:
Commands and results:
```

## Self-review

- [ ] The diff contains only work related to the issue
- [ ] Locking, wake-up, and cleanup paths were reviewed
- [ ] User-visible behavior and UAPI changes are documented
- [ ] Tests would fail without the intended change
- [ ] Known limitations are recorded
- [ ] New source files include `SPDX-License-Identifier: MIT`
- [ ] Kernel module changes preserve `GPL-2.0-only OR MIT`
- [ ] User-visible changes are recorded in `CHANGELOG.md`
