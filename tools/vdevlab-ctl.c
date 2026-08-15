// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "../include/vdevlab.h"

#define VDEVLAB_DEVICE "/dev/vdevlab0"

static void usage(const char *prog)
{
	fprintf(stderr,
		"Usage:\n"
		"  %s get\n"
		"  %s clear\n"
		"  %s set none\n"
		"  %s set eio\n"
		"  %s set delay <milliseconds>\n"
		"  %s set disconnect\n",
		prog, prog, prog, prog, prog, prog);
}

static const char *fault_name(unsigned int type)
{
	switch (type) {
	case VDEVLAB_FAULT_NONE:
		return "none";
	case VDEVLAB_FAULT_EIO:
		return "eio";
	case VDEVLAB_FAULT_DELAY:
		return "delay";
	case VDEVLAB_FAULT_DISCONNECT:
		return "disconnect";
	default:
		return "unknown";
	}
}

int main(int argc, char **argv)
{
	struct vdevlab_fault_config config = {0};
	char *end;
	long delay;
	int fd;
	int ret = 1;

	if (argc < 2) {
		usage(argv[0]);
		return 1;
	}

	fd = open(VDEVLAB_DEVICE, O_RDWR);
	if (fd < 0) {
		perror("open");
		return 1;
	}

	if (!strcmp(argv[1], "get")) {
		if (ioctl(fd, VDEVLAB_IOC_GET_FAULT, &config) < 0) {
			perror("ioctl(GET_FAULT)");
			goto out;
		}

		printf("fault=%s", fault_name(config.type));
		if (config.type == VDEVLAB_FAULT_DELAY)
			printf(" delay_ms=%u", config.delay_ms);
		putchar('\n');
		ret = 0;
		goto out;
	}

	if (!strcmp(argv[1], "clear")) {
		if (ioctl(fd, VDEVLAB_IOC_CLEAR_FAULT) < 0) {
			perror("ioctl(CLEAR_FAULT)");
			goto out;
		}

		printf("fault cleared\n");
		ret = 0;
		goto out;
	}

	if (strcmp(argv[1], "set") || argc < 3) {
		usage(argv[0]);
		goto out;
	}

	if (!strcmp(argv[2], "none")) {
		config.type = VDEVLAB_FAULT_NONE;
	} else if (!strcmp(argv[2], "eio")) {
		config.type = VDEVLAB_FAULT_EIO;
	} else if (!strcmp(argv[2], "disconnect")) {
		config.type = VDEVLAB_FAULT_DISCONNECT;
	} else if (!strcmp(argv[2], "delay")) {
		if (argc != 4) {
			usage(argv[0]);
			goto out;
		}

		errno = 0;
		delay = strtol(argv[3], &end, 10);
		if (errno || *end != '\0' || delay <= 0 || delay > 10000) {
			fprintf(stderr, "delay must be between 1 and 10000 ms\n");
			goto out;
		}

		config.type = VDEVLAB_FAULT_DELAY;
		config.delay_ms = (unsigned int)delay;
	} else {
		usage(argv[0]);
		goto out;
	}

	if (ioctl(fd, VDEVLAB_IOC_SET_FAULT, &config) < 0) {
		perror("ioctl(SET_FAULT)");
		goto out;
	}

	printf("fault=%s", fault_name(config.type));
	if (config.type == VDEVLAB_FAULT_DELAY)
		printf(" delay_ms=%u", config.delay_ms);
	printf("\n");
	ret = 0;

out:
	close(fd);
	return ret;
}
