Karton
======

Karton is a tool to transparently run Linux programs on macOS or on another Linux distro.

``` sh
# Run the compiler on the host machine (running macOS):
$ gcc -o test-mac test.c
$ file test-mac
test-mac: Mach-O 64-bit executable x86_64

# Run the compiler inside Ubuntu using Karton:
$ karton run ubuntu gcc -o test-linux test.c
$ file test-linux
test-linux: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 2.6.32, BuildID[sha1]=5d842663aa0478ba923ce230fe71fcfd07402dba, not stripped
```

In the example, by prefixing your commands with `karton run ubuntu`, you can run them on Ubuntu even if you are using macOS. Files are shared across the two operating systems and executing commands like this is very fast, making the whole experience smooth.

Underneath, Karton uses Docker to allow running programs, but Docker was not designed with this use case in mind, so Karton makes it work.


Why?
----

At work I use Linux, while my personal computer is a Mac. I want to be able to work from home without having to always take my work laptop back home.

Karton is not limited to running Linux programs on macOS but also allows running programs on a different Linux distro (for instance, if you use CentOS but you need to test something on Ubuntu) or running different architectures.


How does it work?
-----------------

The first option I considered was doing Linux development in a virtual machine, but this didn't match the experience I wanted. I want to be able to barely notice I'm running programs on a different operating system, and I want to be able to access my files with all the tools I have on my computer's operating system.

Docker is a project used to automate the deployment of applications inside software containers. A container _appears_ to run an isolated copy of an operating system.<br>
This can be used to run Linux programs on a different operating system or distro, but, like VMs, doesn't really provide the user experience I needed because it's designed mainly to run services and to spawn new instances of the services transparently.

An example of a limitation of normal Docker for this use case is that, every time you run a command, another container instance is spawned.<br>
Imagine, for instance, that you are running a program in a terminal tab and you want to attach a debugger to it from another terminal tab. If you run the Docker commands in the two terminals, then you get _two separate instances of the container_, that is, what appears to be two completely different instances of the operating system. This means that the debugger cannot access your program.

Karton uses Docker to create a semi-permanent container where all the commands are executed. The management of this container is transparent to the user who doesn't need to worry about the Docker-related details.<br>
Karton images can also be easily configured to share files or directory with your host system.
