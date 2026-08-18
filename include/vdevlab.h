// SPDX-License-Identifier: GPL-2.0-only
#ifndef VDEVLAB_H
#define VDEVLAB_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define VDEVLAB_MAX_DELAY_MS      10000U
#define VDEVLAB_MAX_FAULT_REPEAT  1000000U
#define VDEVLAB_MAX_PARTIAL_READ  4096U

enum vdevlab_fault_type {
	VDEVLAB_FAULT_NONE = 0,
	VDEVLAB_FAULT_EIO = 1,
	VDEVLAB_FAULT_DELAY = 2,
	VDEVLAB_FAULT_DISCONNECT = 3,
	VDEVLAB_FAULT_PARTIAL_READ = 4,
};

struct vdevlab_fault_config {
	__u32 type;
	__u32 repeat;
	__u32 delay_ms;
	__u32 partial_read_bytes;
};

#define VDEVLAB_IOC_MAGIC        'V'
#define VDEVLAB_IOC_SET_FAULT    _IOW(VDEVLAB_IOC_MAGIC, 0x01, struct vdevlab_fault_config)
#define VDEVLAB_IOC_GET_FAULT    _IOR(VDEVLAB_IOC_MAGIC, 0x02, struct vdevlab_fault_config)
#define VDEVLAB_IOC_CLEAR_FAULT  _IO(VDEVLAB_IOC_MAGIC, 0x03)
#define VDEVLAB_IOC_RESET        _IO(VDEVLAB_IOC_MAGIC, 0x04)

#endif /* VDEVLAB_H */
