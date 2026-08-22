# SPDX-License-Identifier: MIT

CC ?= cc
CPPFLAGS += -I../include
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror
LDLIBS += -pthread

TARGET := vdevlab-contract-test

.PHONY: all clean

all: $(TARGET)

$(TARGET): vdevlab-contract-test.c ../include/vdevlab.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(LDLIBS) -o $@

clean:
	$(RM) $(TARGET)
