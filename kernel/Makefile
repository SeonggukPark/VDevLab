# SPDX-License-Identifier: MIT

obj-m += vdevlab_core.o
ccflags-y += -I$(src)/../include

KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
