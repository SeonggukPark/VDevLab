# SPDX-License-Identifier: GPL-2.0-only

CC ?= cc
CPPFLAGS += -I../include
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror

TARGET := vtemp-monitor

.PHONY: all clean

all: $(TARGET)

$(TARGET): vtemp_monitor.c ../include/vdevlab.h
	$(CC) $(CPPFLAGS) $(CFLAGS) vtemp_monitor.c -o $@

clean:
	rm -f $(TARGET)
