# SPDX-License-Identifier: GPL-2.0-only

CC ?= cc
CPPFLAGS += -I../include
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror

TARGET := vdevlab-ctl

.PHONY: all clean

all: $(TARGET)

$(TARGET): vdevlab-ctl.c ../include/vdevlab.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@

clean:
	$(RM) $(TARGET)
