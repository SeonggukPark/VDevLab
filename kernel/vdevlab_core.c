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
#include <linux/module.h>
#include <linux/version.h>

#define VDEVLAB_DEVICE_NAME "vdevlab0"
#define VDEVLAB_CLASS_NAME  "vdevlab"

static dev_t vdevlab_dev;
static struct cdev vdevlab_cdev;
static struct class *vdevlab_class;
static struct device *vdevlab_device;

static int vdevlab_open(struct inode *inode, struct file *file)
{
	return 0;
}

static int vdevlab_release(struct inode *inode, struct file *file)
{
	return 0;
}

static const struct file_operations vdevlab_fops = {
	.owner = THIS_MODULE,
	.open = vdevlab_open,
	.release = vdevlab_release,
	.llseek = no_llseek,
};

static int __init vdevlab_init(void)
{
	int ret;

	ret = alloc_chrdev_region(&vdevlab_dev, 0, 1, VDEVLAB_DEVICE_NAME);
	if (ret) {
		pr_err("vdevlab: failed to allocate device number: %d\n", ret);
		return ret;
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

	pr_info("vdevlab: /dev/%s registered (major=%u, minor=%u)\n",
		VDEVLAB_DEVICE_NAME, MAJOR(vdevlab_dev), MINOR(vdevlab_dev));
	return 0;

err_destroy_class:
	class_destroy(vdevlab_class);
err_del_cdev:
	cdev_del(&vdevlab_cdev);
err_unregister_chrdev:
	unregister_chrdev_region(vdevlab_dev, 1);
	return ret;
}

static void __exit vdevlab_exit(void)
{
	device_destroy(vdevlab_class, vdevlab_dev);
	class_destroy(vdevlab_class);
	cdev_del(&vdevlab_cdev);
	unregister_chrdev_region(vdevlab_dev, 1);

	pr_info("vdevlab: /dev/%s unregistered\n", VDEVLAB_DEVICE_NAME);
}

module_init(vdevlab_init);
module_exit(vdevlab_exit);

MODULE_AUTHOR("VDevLab contributors");
MODULE_DESCRIPTION("VDevLab virtual character device core");
MODULE_LICENSE("GPL");
