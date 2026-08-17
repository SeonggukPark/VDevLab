// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include "vdevlab.h"

#define VDEVLAB_DEVICE "/dev/vdevlab0"
#define JOIN_TIMEOUT_SECONDS 2

struct blocked_read {
	int fd;
	pthread_mutex_t lock;
	pthread_cond_t ready_cond;
	bool ready;
	ssize_t result;
	int error;
};

struct blocked_poll {
	int fd;
	pthread_mutex_t lock;
	pthread_cond_t ready_cond;
	bool ready;
	int result;
	short revents;
	int error;
};

static int clear_fault(int fd)
{
	if (ioctl(fd, VDEVLAB_IOC_CLEAR_FAULT) < 0) {
		perror("ioctl(CLEAR_FAULT)");
		return -1;
	}

	return 0;
}

static int set_fault(int fd, unsigned int type, unsigned int repeat,
		     unsigned int delay_ms)
{
	struct vdevlab_fault_config config = {
		.type = type,
		.repeat = repeat,
		.delay_ms = delay_ms,
	};

	if (ioctl(fd, VDEVLAB_IOC_SET_FAULT, &config) < 0) {
		perror("ioctl(SET_FAULT)");
		return -1;
	}

	return 0;
}

static int get_fault(int fd, struct vdevlab_fault_config *config)
{
	if (ioctl(fd, VDEVLAB_IOC_GET_FAULT, config) < 0) {
		perror("ioctl(GET_FAULT)");
		return -1;
	}

	return 0;
}

static int drain_fifo(int fd)
{
	char buffer[256];
	ssize_t result;

	for (;;) {
		result = read(fd, buffer, sizeof(buffer));
		if (result > 0)
			continue;
		if (result < 0 && errno == EAGAIN)
			return 0;

		if (result < 0)
			perror("drain read");
		else
			fprintf(stderr, "drain read returned an unexpected EOF\n");
		return -1;
	}
}

static int expect_poll_error(int fd)
{
	struct pollfd pollfd = {
		.fd = fd,
		.events = POLLIN,
	};
	int result;

	result = poll(&pollfd, 1, 1000);
	if (result != 1) {
		fprintf(stderr, "poll: expected one ready fd, got %d\n", result);
		return -1;
	}
	if (!(pollfd.revents & POLLERR)) {
		fprintf(stderr, "poll: expected POLLERR, got revents=0x%x\n",
			pollfd.revents);
		return -1;
	}

	return 0;
}

static int test_counted_eio(int fd)
{
	static const char payload[] = "READY\n";
	struct vdevlab_fault_config config;
	char buffer[sizeof(payload)] = {0};
	ssize_t result;
	unsigned int attempt;

	if (clear_fault(fd) < 0 || drain_fifo(fd) < 0)
		return -1;
	if (set_fault(fd, VDEVLAB_FAULT_EIO, 3, 0) < 0)
		return -1;

	result = write(fd, payload, sizeof(payload) - 1);
	if (result != (ssize_t)(sizeof(payload) - 1)) {
		fprintf(stderr, "write: EIO setup consumed the injection write\n");
		return -1;
	}

	if (get_fault(fd, &config) < 0)
		return -1;
	if (config.type != VDEVLAB_FAULT_EIO || config.repeat != 3) {
		fprintf(stderr,
			"write: expected EIO remaining=3, got type=%u remaining=%u\n",
			config.type, config.repeat);
		return -1;
	}

	if (expect_poll_error(fd) < 0)
		return -1;

	for (attempt = 1; attempt <= 3; attempt++) {
		errno = 0;
		result = read(fd, buffer, sizeof(buffer));
		if (result != -1 || errno != EIO) {
			fprintf(stderr,
				"read %u: expected -EIO, got result=%zd errno=%d\n",
				attempt, result, errno);
			return -1;
		}

		if (get_fault(fd, &config) < 0)
			return -1;

		if (attempt < 3) {
			unsigned int expected = 3 - attempt;

			if (config.type != VDEVLAB_FAULT_EIO ||
			    config.repeat != expected) {
				fprintf(stderr,
					"read %u: expected remaining=%u, got type=%u remaining=%u\n",
					attempt, expected, config.type,
					config.repeat);
				return -1;
			}
		} else if (config.type != VDEVLAB_FAULT_NONE || config.repeat != 0) {
			fprintf(stderr,
				"read 3: fault did not automatically return to NONE\n");
			return -1;
		}
	}

	result = read(fd, buffer, sizeof(buffer));
	if (result != (ssize_t)(sizeof(payload) - 1) ||
	    memcmp(buffer, payload, sizeof(payload) - 1) != 0) {
		fprintf(stderr, "recovery read: payload mismatch or wrong length\n");
		return -1;
	}

	puts("PASS counted-eio: expected=3 observed=3 write-consumed=0");
	puts("PASS auto-recovery: fourth read returned queued payload");
	return 0;
}

static int test_invalid_config_preserves_state(int fd)
{
	struct vdevlab_fault_config invalid = {
		.type = VDEVLAB_FAULT_EIO,
		.repeat = 0,
	};
	struct vdevlab_fault_config observed;

	if (set_fault(fd, VDEVLAB_FAULT_DELAY, 0, 25) < 0)
		return -1;

	errno = 0;
	if (ioctl(fd, VDEVLAB_IOC_SET_FAULT, &invalid) != -1 || errno != EINVAL) {
		fprintf(stderr, "invalid config: expected -EINVAL for repeat=0\n");
		return -1;
	}

	if (get_fault(fd, &observed) < 0)
		return -1;
	if (observed.type != VDEVLAB_FAULT_DELAY || observed.delay_ms != 25) {
		fprintf(stderr, "invalid config changed the active fault\n");
		return -1;
	}

	if (clear_fault(fd) < 0)
		return -1;

	puts("PASS invalid-config: rejected without changing active state");
	return 0;
}

static void *blocking_read_main(void *data)
{
	struct blocked_read *blocked = data;
	char byte;

	pthread_mutex_lock(&blocked->lock);
	blocked->ready = true;
	pthread_cond_signal(&blocked->ready_cond);
	pthread_mutex_unlock(&blocked->lock);

	errno = 0;
	blocked->result = read(blocked->fd, &byte, sizeof(byte));
	blocked->error = errno;
	return NULL;
}

static int test_blocked_read_wakeup(int control_fd)
{
	struct blocked_read blocked = {
		.fd = -1,
		.lock = PTHREAD_MUTEX_INITIALIZER,
		.ready_cond = PTHREAD_COND_INITIALIZER,
	};
	struct timespec delay = {
		.tv_nsec = 100 * 1000 * 1000,
	};
	struct timespec deadline;
	pthread_t thread;
	int join_result;
	int result = -1;

	if (clear_fault(control_fd) < 0 || drain_fifo(control_fd) < 0)
		goto out_destroy;

	blocked.fd = open(VDEVLAB_DEVICE, O_RDONLY);
	if (blocked.fd < 0) {
		perror("open blocking reader");
		goto out_destroy;
	}

	join_result = pthread_create(&thread, NULL, blocking_read_main, &blocked);
	if (join_result != 0) {
		fprintf(stderr, "pthread_create: %s\n", strerror(join_result));
		goto out_close;
	}

	pthread_mutex_lock(&blocked.lock);
	while (!blocked.ready)
		pthread_cond_wait(&blocked.ready_cond, &blocked.lock);
	pthread_mutex_unlock(&blocked.lock);

	nanosleep(&delay, NULL);
	if (set_fault(control_fd, VDEVLAB_FAULT_EIO, 1, 0) < 0)
		goto out_cancel;

	clock_gettime(CLOCK_REALTIME, &deadline);
	deadline.tv_sec += JOIN_TIMEOUT_SECONDS;
	join_result = pthread_timedjoin_np(thread, NULL, &deadline);
	if (join_result != 0) {
		fprintf(stderr, "blocked read did not wake: %s\n",
			strerror(join_result));
		goto out_cancel;
	}

	if (blocked.result != -1 || blocked.error != EIO) {
		fprintf(stderr,
			"blocked read: expected -EIO, got result=%zd errno=%d\n",
			blocked.result, blocked.error);
		goto out_close;
	}

	puts("PASS blocked-read: EIO activation woke sleeping reader");
	result = 0;
	goto out_close;

out_cancel:
	clear_fault(control_fd);
	pthread_cancel(thread);
	pthread_join(thread, NULL);
out_close:
	close(blocked.fd);
out_destroy:
	pthread_cond_destroy(&blocked.ready_cond);
	pthread_mutex_destroy(&blocked.lock);
	return result;
}

static void *blocking_poll_main(void *data)
{
	struct blocked_poll *blocked = data;
	struct pollfd pollfd = {
		.fd = blocked->fd,
		.events = POLLIN,
	};

	pthread_mutex_lock(&blocked->lock);
	blocked->ready = true;
	pthread_cond_signal(&blocked->ready_cond);
	pthread_mutex_unlock(&blocked->lock);

	errno = 0;
	blocked->result = poll(&pollfd, 1, 2000);
	blocked->error = errno;
	blocked->revents = pollfd.revents;
	return NULL;
}

static int test_blocked_poll_wakeup(int control_fd)
{
	struct blocked_poll blocked = {
		.fd = control_fd,
		.lock = PTHREAD_MUTEX_INITIALIZER,
		.ready_cond = PTHREAD_COND_INITIALIZER,
	};
	struct timespec delay = {
		.tv_nsec = 100 * 1000 * 1000,
	};
	struct timespec deadline;
	pthread_t thread;
	int join_result;
	int result = -1;

	if (clear_fault(control_fd) < 0 || drain_fifo(control_fd) < 0)
		goto out_destroy;

	join_result = pthread_create(&thread, NULL, blocking_poll_main, &blocked);
	if (join_result != 0) {
		fprintf(stderr, "pthread_create: %s\n", strerror(join_result));
		goto out_destroy;
	}

	pthread_mutex_lock(&blocked.lock);
	while (!blocked.ready)
		pthread_cond_wait(&blocked.ready_cond, &blocked.lock);
	pthread_mutex_unlock(&blocked.lock);

	nanosleep(&delay, NULL);
	if (set_fault(control_fd, VDEVLAB_FAULT_EIO, 1, 0) < 0)
		goto out_cancel;

	clock_gettime(CLOCK_REALTIME, &deadline);
	deadline.tv_sec += JOIN_TIMEOUT_SECONDS + 1;
	join_result = pthread_timedjoin_np(thread, NULL, &deadline);
	if (join_result != 0) {
		fprintf(stderr, "blocked poll did not wake: %s\n",
			strerror(join_result));
		goto out_cancel;
	}

	if (blocked.result != 1 || !(blocked.revents & POLLERR)) {
		fprintf(stderr,
			"blocked poll: expected POLLERR, got result=%d revents=0x%x errno=%d\n",
			blocked.result, blocked.revents, blocked.error);
		goto out_destroy;
	}

	if (clear_fault(control_fd) < 0)
		goto out_destroy;

	puts("PASS blocked-poll: EIO activation woke poll with POLLERR");
	result = 0;
	goto out_destroy;

out_cancel:
	clear_fault(control_fd);
	pthread_cancel(thread);
	pthread_join(thread, NULL);
out_destroy:
	pthread_cond_destroy(&blocked.ready_cond);
	pthread_mutex_destroy(&blocked.lock);
	return result;
}

int main(void)
{
	int fd;
	int result = 1;

	fd = open(VDEVLAB_DEVICE, O_RDWR | O_NONBLOCK);
	if (fd < 0) {
		perror("open " VDEVLAB_DEVICE);
		return 1;
	}

	if (test_counted_eio(fd) < 0)
		goto out;
	if (test_invalid_config_preserves_state(fd) < 0)
		goto out;
	if (test_blocked_read_wakeup(fd) < 0)
		goto out;
	if (test_blocked_poll_wakeup(fd) < 0)
		goto out;

	puts("PASS deterministic fault contract suite");
	result = 0;

out:
	clear_fault(fd);
	close(fd);
	return result;
}
