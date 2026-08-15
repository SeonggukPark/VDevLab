// SPDX-License-Identifier: GPL-2.0-only
/*
 * VDevLab - virtual device test framework
 *
 * Copyright (C) 2026 VDevLab contributors
 */

#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/kfifo.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/poll.h>
#include <linux/version.h>
#include <linux/wait.h>

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

static int vdevlab_open(struct inode *inode, struct file *file)
{
	return 0;
}

static int vdevlab_release(struct inode *inode, struct file *file)
{
	return 0;
}

static ssize_t vdevlab_read(struct file *file, char __user *buf,
			   size_t count, loff_t *ppos)
{
	unsigned int copied = 0;
	unsigned int to_copy;
	int ret;

	if (!count)
		return 0;

	for (;;) {
		if (file->f_flags & O_NONBLOCK) {
			if (kfifo_is_empty(&vdevlab_fifo))
				return -EAGAIN;
		} else {
			ret = wait_event_interruptible(vdevlab_readq,
						       !kfifo_is_empty(&vdevlab_fifo));
			if (ret)
				return ret;
		}

		ret = mutex_lock_interruptible(&vdevlab_fifo_lock);
		if (ret)
			return ret;

		if (!kfifo_is_empty(&vdevlab_fifo))
			break;

		mutex_unlock(&vdevlab_fifo_lock);

		if (file->f_flags & O_NONBLOCK)
			return -EAGAIN;
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
		if (file->f_flags & O_NONBLOCK) {
			if (kfifo_is_full(&vdevlab_fifo))
				return -EAGAIN;
		} else {
			ret = wait_event_interruptible(vdevlab_writeq,
						       !kfifo_is_full(&vdevlab_fifo));
			if (ret)
				return ret;
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
	__poll_t mask = 0;

	poll_wait(file, &vdevlab_readq, wait);
	poll_wait(file, &vdevlab_writeq, wait);

	mutex_lock(&vdevlab_fifo_lock);

	if (!kfifo_is_empty(&vdevlab_fifo))
		mask |= EPOLLIN | EPOLLRDNORM;

	if (!kfifo_is_full(&vdevlab_fifo))
		mask |= EPOLLOUT | EPOLLWRNORM;

	mutex_unlock(&vdevlab_fifo_lock);

	return mask;
}

static const struct file_operations vdevlab_fops = {
	.owner = THIS_MODULE,
	.open = vdevlab_open,
	.release = vdevlab_release,
	.read = vdevlab_read,
	.write = vdevlab_write,
	.poll = vdevlab_poll,
	.llseek = no_llseek,
};

static int __init vdevlab_init(void)
{
	int ret;

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
