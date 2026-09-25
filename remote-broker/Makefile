CC ?= arm-linux-gnueabi-gcc
CFLAGS ?= -Os -std=gnu99 -Wall -Wextra -Werror -D_FILE_OFFSET_BITS=64
LDFLAGS ?= -static

.PHONY: all clean

all: remote-broker

remote-broker: remote-broker.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<

clean:
	rm -f remote-broker
