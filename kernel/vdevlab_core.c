// SPDX-License-Identifier: GPL-2.0-only
/*
 * VDevLab - virtual device test framework
 *
 * Copyright (C) 2026 VDevLab contributors
 */

#include <linux/cdev.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/kfifo.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/poll.h>
#include <linux/uaccess.h>
#include <linux/version.h>
#include <linux/wait.h>

#include "vdevlab.h"

#define VDEVLAB_DEVICE_NAME "vdevlab0"
#define VDEVLAB_CLASS_NAME  "vdevlab"
#define VDEVLAB_FIFO_SIZE   4096

static dev_t vdevlab_dev;
static struct cdev vdevlab_cdev;
static struct class *vdevlab_class;
static struct device *vdevlab_device;

static struct kfifo vdevlab_fifo;
static DEFINE_MUTEX(vdevlab_fifo_lock);
static DECLARE_WAIT_QUEUE_HEAD(vdevlab_readq);
static DECLARE_WAIT_QUEUE_HEAD(vdevlab_writeq);

static struct vdevlab_fault_config vdevlab_fault;
static DEFINE_MUTEX(vdevlab_fault_lock);

static void vdevlab_clear_fault_locked(void)
{
	vdevlab_fault.type = VDEVLAB_FAULT_NONE;
	vdevlab_fault.repeat = 0;
	vdevlab_fault.delay_ms = 0;
}

static bool vdevlab_fault_interrupts_read(void)
{
	u32 type = READ_ONCE(vdevlab_fault.type);

	return type == VDEVLAB_FAULT_EIO ||
	       type == VDEVLAB_FAULT_DISCONNECT;
}

static bool vdevlab_is_disconnected(void)
{
	return READ_ONCE(vdevlab_fault.type) == VDEVLAB_FAULT_DISCONNECT;
}

static int vdevlab_open(struct inode *inode, struct file *file)
{
	return 0;
}

static int vdevlab_release(struct inode *inode, struct file *file)
{
	return 0;
}

/*
 * Data faults belong to the consumer-facing read path.  Keeping writes fault
 * free prevents a scenario runner from consuming an EIO intended for the
 * application under test.  Disconnect remains a device-wide state.
 */
static int vdevlab_apply_read_fault(bool *delay_applied)
{
	unsigned int delay_ms = 0;
	int ret = 0;

	mutex_lock(&vdevlab_fault_lock);
	switch (vdevlab_fault.type) {
	case VDEVLAB_FAULT_NONE:
		break;
	case VDEVLAB_FAULT_EIO:
		if (!vdevlab_fault.repeat) {
			vdevlab_clear_fault_locked();
			break;
		}

		vdevlab_fault.repeat--;
		if (!vdevlab_fault.repeat)
			vdevlab_clear_fault_locked();
		ret = -EIO;
		break;
	case VDEVLAB_FAULT_DELAY:
		if (!*delay_applied) {
			delay_ms = vdevlab_fault.delay_ms;
			*delay_applied = true;
		}
		break;
	case VDEVLAB_FAULT_DISCONNECT:
		ret = -ENODEV;
		break;
	default:
		ret = -EINVAL;
		break;
	}
	mutex_unlock(&vdevlab_fault_lock);

	if (delay_ms && msleep_interruptible(delay_ms))
		return -ERESTARTSYS;

	return ret;
}

static ssize_t vdevlab_read(struct file *file, char __user *buf,
			   size_t count, loff_t *ppos)
{
	unsigned int copied = 0;
	unsigned int to_copy;
	bool delay_applied = false;
	int ret;

	if (!count)
		return 0;

	for (;;) {
		ret = vdevlab_apply_read_fault(&delay_applied);
		if (ret)
			return ret;

		ret = mutex_lock_interruptible(&vdevlab_fifo_lock);
		if (ret)
			return ret;

		if (!kfifo_is_empty(&vdevlab_fifo))
			break;

		mutex_unlock(&vdevlab_fifo_lock);

		if (file->f_flags & O_NONBLOCK)
			return -EAGAIN;

		ret = wait_event_interruptible(vdevlab_readq,
					       !kfifo_is_empty(&vdevlab_fifo) ||
					       vdevlab_fault_interrupts_read());
		if (ret)
			return ret;
	}

	to_copy = min_t(size_t, count, kfifo_len(&vdevlab_fifo));
	ret = kfifo_to_user(&vdevlab_fifo, buf, to_copy, &copied);
	mutex_unlock(&vdevlab_fifo_lock);

	if (copied)
		wake_up_interruptible(&vdevlab_writeq);

	if (ret)
		return copied ? copied : ret;

	return copied;
}

static ssize_t vdevlab_write(struct file *file, const char __user *buf,
			    size_t count, loff_t *ppos)
{
	unsigned int copied = 0;
	unsigned int to_copy;
	int ret;

	if (!count)
		return 0;

	for (;;) {
		if (vdevlab_is_disconnected())
			return -ENODEV;

		if (file->f_flags & O_NONBLOCK) {
			if (kfifo_is_full(&vdevlab_fifo))
				return -EAGAIN;
		} else {
			ret = wait_event_interruptible(vdevlab_writeq,
						       !kfifo_is_full(&vdevlab_fifo) ||
						       vdevlab_is_disconnected());
			if (ret)
				return ret;
			if (vdevlab_is_disconnected())
				continue;
		}

		ret = mutex_lock_interruptible(&vdevlab_fifo_lock);
		if (ret)
			return ret;

		if (!kfifo_is_full(&vdevlab_fifo))
			break;

		mutex_unlock(&vdevlab_fifo_lock);

		if (file->f_flags & O_NONBLOCK)
			return -EAGAIN;
	}

	to_copy = min_t(size_t, count, kfifo_avail(&vdevlab_fifo));
	ret = kfifo_from_user(&vdevlab_fifo, buf, to_copy, &copied);
	mutex_unlock(&vdevlab_fifo_lock);

	if (copied)
		wake_up_interruptible(&vdevlab_readq);

	if (ret)
		return copied ? copied : ret;

	return copied;
}

static __poll_t vdevlab_poll(struct file *file, poll_table *wait)
{
	u32 fault_type;
	__poll_t mask = 0;

	poll_wait(file, &vdevlab_readq, wait);
	poll_wait(file, &vdevlab_writeq, wait);

	fault_type = READ_ONCE(vdevlab_fault.type);

	if (fault_type == VDEVLAB_FAULT_DISCONNECT)
		return EPOLLERR | EPOLLHUP;
	if (fault_type == VDEVLAB_FAULT_EIO)
		return EPOLLERR;

	mutex_lock(&vdevlab_fifo_lock);

	if (!kfifo_is_empty(&vdevlab_fifo))
		mask |= EPOLLIN | EPOLLRDNORM;

	if (!kfifo_is_full(&vdevlab_fifo))
		mask |= EPOLLOUT | EPOLLWRNORM;

	mutex_unlock(&vdevlab_fifo_lock);

	return mask;
}

static long vdevlab_ioctl(struct file *file, unsigned int cmd,
			  unsigned long arg)
{
	struct vdevlab_fault_config config;

	switch (cmd) {
	case VDEVLAB_IOC_SET_FAULT:
		if (copy_from_user(&config, (void __user *)arg, sizeof(config)))
			return -EFAULT;

		if (config.type > VDEVLAB_FAULT_DISCONNECT)
			return -EINVAL;

		switch (config.type) {
		case VDEVLAB_FAULT_NONE:
			config.repeat = 0;
			config.delay_ms = 0;
			break;
		case VDEVLAB_FAULT_EIO:
			if (!config.repeat ||
			    config.repeat > VDEVLAB_MAX_FAULT_REPEAT)
				return -EINVAL;
			config.delay_ms = 0;
			break;
		case VDEVLAB_FAULT_DELAY:
			if (!config.delay_ms || config.delay_ms > VDEVLAB_MAX_DELAY_MS)
				return -EINVAL;
			config.repeat = 0;
			break;
		case VDEVLAB_FAULT_DISCONNECT:
			config.repeat = 0;
			config.delay_ms = 0;
			break;
		default:
			return -EINVAL;
		}

		mutex_lock(&vdevlab_fault_lock);
		vdevlab_fault = config;
		mutex_unlock(&vdevlab_fault_lock);

		wake_up_interruptible(&vdevlab_readq);
		wake_up_interruptible(&vdevlab_writeq);
		return 0;

	case VDEVLAB_IOC_GET_FAULT:
		mutex_lock(&vdevlab_fault_lock);
		config = vdevlab_fault;
		mutex_unlock(&vdevlab_fault_lock);

		if (copy_to_user((void __user *)arg, &config, sizeof(config)))
			return -EFAULT;
		return 0;

	case VDEVLAB_IOC_CLEAR_FAULT:
		mutex_lock(&vdevlab_fault_lock);
		vdevlab_clear_fault_locked();
		mutex_unlock(&vdevlab_fault_lock);

		wake_up_interruptible(&vdevlab_readq);
		wake_up_interruptible(&vdevlab_writeq);
		return 0;

	default:
		return -ENOTTY;
	}
}

static const struct file_operations vdevlab_fops = {
	.owner = THIS_MODULE,
	.open = vdevlab_open,
	.release = vdevlab_release,
	.read = vdevlab_read,
	.write = vdevlab_write,
	.poll = vdevlab_poll,
	.unlocked_ioctl = vdevlab_ioctl,
	.llseek = no_llseek,
};

static int __init vdevlab_init(void)
{
	int ret;

	mutex_lock(&vdevlab_fault_lock);
	vdevlab_clear_fault_locked();
	mutex_unlock(&vdevlab_fault_lock);

	ret = kfifo_alloc(&vdevlab_fifo, VDEVLAB_FIFO_SIZE, GFP_KERNEL);
	if (ret) {
		pr_err("vdevlab: failed to allocate FIFO: %d\n", ret);
		return ret;
	}

	ret = alloc_chrdev_region(&vdevlab_dev, 0, 1, VDEVLAB_DEVICE_NAME);
	if (ret) {
		pr_err("vdevlab: failed to allocate device number: %d\n", ret);
		goto err_free_fifo;
	}

	cdev_init(&vdevlab_cdev, &vdevlab_fops);
	vdevlab_cdev.owner = THIS_MODULE;

	ret = cdev_add(&vdevlab_cdev, vdevlab_dev, 1);
	if (ret) {
		pr_err("vdevlab: failed to add character device: %d\n", ret);
		goto err_unregister_chrdev;
	}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
	vdevlab_class = class_create(VDEVLAB_CLASS_NAME);
#else
	vdevlab_class = class_create(THIS_MODULE, VDEVLAB_CLASS_NAME);
#endif
	if (IS_ERR(vdevlab_class)) {
		ret = PTR_ERR(vdevlab_class);
		pr_err("vdevlab: failed to create device class: %d\n", ret);
		goto err_del_cdev;
	}

	vdevlab_device = device_create(vdevlab_class, NULL, vdevlab_dev, NULL,
					 VDEVLAB_DEVICE_NAME);
	if (IS_ERR(vdevlab_device)) {
		ret = PTR_ERR(vdevlab_device);
		pr_err("vdevlab: failed to create device: %d\n", ret);
		goto err_destroy_class;
	}

	pr_info("vdevlab: /dev/%s registered (major=%u, minor=%u, fifo=%u bytes)\n",
		VDEVLAB_DEVICE_NAME, MAJOR(vdevlab_dev), MINOR(vdevlab_dev),
		VDEVLAB_FIFO_SIZE);
	return 0;

err_destroy_class:
	class_destroy(vdevlab_class);
err_del_cdev:
	cdev_del(&vdevlab_cdev);
err_unregister_chrdev:
	unregister_chrdev_region(vdevlab_dev, 1);
err_free_fifo:
	kfifo_free(&vdevlab_fifo);
	return ret;
}

static void __exit vdevlab_exit(void)
{
	device_destroy(vdevlab_class, vdevlab_dev);
	class_destroy(vdevlab_class);
	cdev_del(&vdevlab_cdev);
	unregister_chrdev_region(vdevlab_dev, 1);
	kfifo_free(&vdevlab_fifo);

	pr_info("vdevlab: /dev/%s unregistered\n", VDEVLAB_DEVICE_NAME);
}

module_init(vdevlab_init);
module_exit(vdevlab_exit);

MODULE_AUTHOR("VDevLab contributors");
MODULE_DESCRIPTION("VDevLab virtual character device core");
MODULE_LICENSE("GPL");
