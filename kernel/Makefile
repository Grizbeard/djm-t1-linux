# Out-of-tree build for the DJM-T1 kernel ALSA driver.
# Needs the running kernel's build tree (linux-headers).
obj-m += djmt1_audio.o

KDIR ?= /lib/modules/$(shell uname -r)/build
PWD  := $(shell pwd)

# Match the kernel's toolchain. Clang-built kernels (Arch/CachyOS, Android, etc.)
# need LLVM=1; pass it through if the caller set it, e.g. `make LLVM=1`.
all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

# For a permanent install, use DKMS (dkms.conf) rather than copying the .ko
# into /lib/modules: DKMS rebuilds it for each new kernel. See README.md.
