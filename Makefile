# SPDX-License-Identifier: GPL-2.0-only

.PHONY: all kernel-module userspace tools tests contract-test clean

all: kernel-module userspace

kernel-module:
	$(MAKE) -C kernel

userspace: tools tests

tools:
	$(MAKE) -C tools

tests:
	$(MAKE) -C tests

contract-test: all
	bash ./scripts/run-kernel-contract-test.sh

clean:
	$(MAKE) -C kernel clean
	$(MAKE) -C tools clean
	$(MAKE) -C tests clean
