# SPDX-License-Identifier: MIT

.PHONY: all kernel-module userspace tools tests examples python-test setup demo contract-test smoke-test clean

all: kernel-module userspace

kernel-module:
	$(MAKE) -C kernel

userspace: tools tests examples

tools:
	$(MAKE) -C tools

tests:
	$(MAKE) -C tests

examples:
	$(MAKE) -C examples

python-test:
	python -m pytest

setup:
	./scripts/setup.sh

demo:
	./scripts/demo.sh

contract-test: all
	bash ./scripts/run-kernel-contract-test.sh

smoke-test: all
	bash ./scripts/run-vtemp-smoke-test.sh

clean:
	$(MAKE) -C kernel clean
	$(MAKE) -C tools clean
	$(MAKE) -C tests clean
	$(MAKE) -C examples clean
