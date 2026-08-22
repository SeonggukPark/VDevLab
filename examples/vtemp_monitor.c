// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_DEVICE "/dev/vdevlab0"
#define DEFAULT_POLL_TIMEOUT_MS 5000
#define MAX_PENDING_BYTES 4096
#define MAX_EIO_RETRIES 3U
#define THERMAL_WARNING_C 80.0

struct options {
	const char *device;
	unsigned int max_events;
	int poll_timeout_ms;
};

struct input_buffer {
	char data[MAX_PENDING_BYTES];
	size_t length;
};

static volatile sig_atomic_t stop_requested;

static long long monotonic_milliseconds(void)
{
	struct timespec now;

	if (clock_gettime(CLOCK_MONOTONIC, &now) < 0)
		return -1;

	return (long long)now.tv_sec * 1000LL + now.tv_nsec / 1000000L;
}

static void log_simple(const char *event)
{
	printf("{\"timestamp_ms\":%lld,\"event\":\"%s\"}\n",
	       monotonic_milliseconds(), event);
	fflush(stdout);
}

static void log_errno_event(const char *event, int error)
{
	printf("{\"timestamp_ms\":%lld,\"event\":\"%s\",\"errno\":%d}\n",
	       monotonic_milliseconds(), event, error);
	fflush(stdout);
}

static void log_retry(unsigned int retry)
{
	printf("{\"timestamp_ms\":%lld,\"event\":\"READ_RETRY\","
	       "\"retry\":%u,\"max_retries\":%u,\"errno\":%d}\n",
	       monotonic_milliseconds(), retry, MAX_EIO_RETRIES, EIO);
	fflush(stdout);
}

static void log_recovery(unsigned int retries)
{
	printf("{\"timestamp_ms\":%lld,\"event\":\"RECOVERY_SUCCESS\","
	       "\"retries\":%u}\n",
	       monotonic_milliseconds(), retries);
	fflush(stdout);
}

static void log_temperature(double temperature)
{
	const char *event = temperature >= THERMAL_WARNING_C ?
		"THERMAL_WARNING" : "TEMPERATURE";

	printf("{\"timestamp_ms\":%lld,\"event\":\"%s\","
	       "\"temperature_c\":%.3f}\n",
	       monotonic_milliseconds(), event, temperature);
	fflush(stdout);
}

static void handle_signal(int signal_number)
{
	(void)signal_number;
	stop_requested = 1;
}

static int parse_unsigned(const char *text, unsigned int *value)
{
	char *end;
	unsigned long parsed;

	errno = 0;
	parsed = strtoul(text, &end, 10);
	if (errno || !*text || *end != '\0' || parsed > UINT_MAX)
		return -1;

	*value = (unsigned int)parsed;
	return 0;
}

static void usage(const char *program)
{
	fprintf(stderr,
		"Usage: %s [--device PATH] [--max-events COUNT] "
		"[--poll-timeout-ms MS]\n",
		program);
}

static int parse_options(int argc, char **argv, struct options *options)
{
	unsigned int value;
	int index;

	options->device = DEFAULT_DEVICE;
	options->max_events = 0;
	options->poll_timeout_ms = DEFAULT_POLL_TIMEOUT_MS;

	for (index = 1; index < argc; index++) {
		if (!strcmp(argv[index], "--device") && index + 1 < argc) {
			options->device = argv[++index];
		} else if (!strcmp(argv[index], "--max-events") &&
			   index + 1 < argc) {
			if (parse_unsigned(argv[++index], &value) < 0 || !value)
				return -1;
			options->max_events = value;
		} else if (!strcmp(argv[index], "--poll-timeout-ms") &&
			   index + 1 < argc) {
			if (parse_unsigned(argv[++index], &value) < 0 ||
			    value > INT_MAX)
				return -1;
			options->poll_timeout_ms = (int)value;
		} else if (!strcmp(argv[index], "--help")) {
			usage(argv[0]);
			exit(0);
		} else {
			return -1;
		}
	}

	return 0;
}

static int process_line(char *line, unsigned int *event_count)
{
	char *start = line;
	char *end;
	double temperature;

	while (*start == ' ' || *start == '\t' || *start == '\r')
		start++;

	errno = 0;
	temperature = strtod(start, &end);
	if (errno || end == start || !isfinite(temperature)) {
		log_simple("INVALID_INPUT");
		return -1;
	}

	while (*end == ' ' || *end == '\t' || *end == '\r')
		end++;
	if (*end != '\0') {
		log_simple("INVALID_INPUT");
		return -1;
	}

	log_temperature(temperature);
	(*event_count)++;
	return 0;
}

static int consume_input(struct input_buffer *input, const char *data,
			 size_t length, unsigned int *event_count,
			 unsigned int max_events)
{
	size_t index;

	for (index = 0; index < length; index++) {
		if (data[index] == '\n') {
			input->data[input->length] = '\0';
			process_line(input->data, event_count);
			input->length = 0;
			if (max_events && *event_count >= max_events)
				return 1;
			continue;
		}

		if (input->length + 1 >= sizeof(input->data)) {
			input->length = 0;
			log_simple("INPUT_TOO_LONG");
			continue;
		}

		input->data[input->length++] = data[index];
	}

	return 0;
}

int main(int argc, char **argv)
{
	struct options options;
	struct input_buffer input = {0};
	struct pollfd descriptor;
	struct sigaction action = {0};
	char read_buffer[512];
	unsigned int event_count = 0;
	unsigned int eio_retries = 0;
	ssize_t bytes_read;
	int poll_result;
	int fd;
	int result = 1;

	if (parse_options(argc, argv, &options) < 0) {
		usage(argv[0]);
		return 2;
	}

	action.sa_handler = handle_signal;
	sigemptyset(&action.sa_mask);
	sigaction(SIGINT, &action, NULL);
	sigaction(SIGTERM, &action, NULL);

	fd = open(options.device, O_RDONLY | O_NONBLOCK);
	if (fd < 0) {
		perror("open");
		return 1;
	}

	descriptor.fd = fd;
	descriptor.events = POLLIN;
	log_simple("MONITOR_STARTED");

	while (!stop_requested) {
		descriptor.revents = 0;
		poll_result = poll(&descriptor, 1, options.poll_timeout_ms);
		if (poll_result < 0) {
			if (errno == EINTR)
				continue;
			perror("poll");
			goto out;
		}
		if (!poll_result)
			continue;
		if (!(descriptor.revents & (POLLIN | POLLERR | POLLHUP)))
			continue;

		errno = 0;
		bytes_read = read(fd, read_buffer, sizeof(read_buffer));
		if (bytes_read < 0) {
			if (errno == EAGAIN)
				continue;
			if (errno == EIO) {
				eio_retries++;
				if (eio_retries > MAX_EIO_RETRIES) {
					log_errno_event("READ_FAILED", EIO);
					goto out;
				}
				log_retry(eio_retries);
				continue;
			}
			if (errno == ENODEV) {
				log_errno_event("DEVICE_DISCONNECTED", ENODEV);
				result = 0;
				goto out;
			}
			log_errno_event("READ_FAILED", errno);
			goto out;
		}
		if (!bytes_read) {
			log_simple("DEVICE_EOF");
			result = 0;
			goto out;
		}

		if (eio_retries) {
			log_recovery(eio_retries);
			eio_retries = 0;
		}
		if (consume_input(&input, read_buffer, (size_t)bytes_read,
				  &event_count, options.max_events)) {
			result = 0;
			goto out;
		}
	}

	result = 0;
out:
	close(fd);
	return result;
}
