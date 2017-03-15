<img align="right" src="https://karton.github.io/img/karton-256.png" width="96px" height="96px">

[[Web site](https://karton.github.io/)] &ndash; [[Install](https://karton.github.io/install.html)] &ndash; [[How to use](https://karton.github.io/how-to-use.html)] &ndash; [[FAQ](https://karton.github.io/faq.html)] &ndash; [[Contribute](https://karton.github.io/contribute.html)]

Karton
======

Karton is a tool to transparently run Linux programs on macOS or on another Linux distro.

``` sh
$ uname -a # Show we are running on macOS.
Darwin my-hostname 16.4.0 Darwin Kernel Version 16.4.0 [...]

$ # Run the compiler in the Ubuntu image we use for work
$ # (which we called "ubuntu-work"):
$ karton run ubuntu-work gcc -o test_linux test.c

$ # Verify that the program is actually a Linux one.
$ # The files are shared and available both on your
$ # system and in the image:
$ file test_linux
test_linux: ELF 64-bit LSB executable, x86-64, [...]

$ # Same thing but on 32-bit ARMv7 (in the image we
$ # called "ubuntu-work-arm"):
$ karton run ubuntu-work-arm gcc -o test_arm test.c
$ file test_arm
test_arm: ELF 32-bit LSB executable, ARM, EABI5 [...]

$ # We can run the ARM program:
$ karton run ubuntu-work-arm ./test_arm
[... Output of our program ...]
```

In another terminal you can attach to the running program and debug it.

``` sh
$ # Find the PID of the test_arm program.
$ karton run ubuntu-work-arm ps aux | grep test_arm
test_arm    42  [...]  test_arm

$ # Debug it!
$ karton run ubuntu-work-arm gdb --pid 42
GNU gdb (Ubuntu 7.11.1-0ubuntu1~16.04) 7.11.1
Copyright (C) 2016 Free Software Foundation, Inc.
[...]
Attaching to process 11
[...]
0x00007f53430e4740 in __nanosleep_nocancel () at ../sysdeps/unix/syscall-template.S:84
84	../sysdeps/unix/syscall-template.S: No such file or directory.
(gdb)
```

In the example, by prefixing your commands with `karton run ubuntu`, you can run them on Ubuntu even if you are using macOS (or another Linux distro!). Files are shared across the two operating systems and executing commands like this is very fast, making the whole experience smooth.

Karton uses Docker 🐳 to create a semi-permanent container where all the commands are executed. The management of this container is transparent to the user, who doesn't need to worry about the Docker-related details.<br>
Karton images can also be easily configured to share files or directory with your host system.
