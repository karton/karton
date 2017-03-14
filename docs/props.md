DefinitionProperties
====================

The `DefinitionProperties` class defines how to generate an image: which packages
to install, which base distro to use, which files and directories to share, etc.



`abspath(path)`
---------------
Make `path` absolute.

If `path` is relative, it is considered relative to the definition file which is
currently being parsed.
If it's already absolute, then nothing is done.

<dl>
<dt><code>path</code>:</dt>
<dd>The path to make absolute if it's relative.
</dd>
<dt>Return value:</dt>
<dd>An absolute path.
</dd>
</dl>

`get_path_mappings()`
---------------------
The list of resources shared between host and guest.

You should call this only after setting things like the home directory location which
could change some of these values.

<dl>
<dt>Return value:</dt>
<dd>A list of tuples.
The first element of the tuple is the location of the shared directory or file on
the host.
The second is the location inside the image.
</dd>
</dl>

`import_definition(other_definition_directory)`
-----------------------------------------------
Import an existing definition file.

<dl>
<dt><code>other_definition_directory</code>:</dt>
<dd>The path of the directory where the definition file is.
It can be an absolute path or a path relative to the current definition file.
</dd>
</dl>

`share_path(host_path, image_path=None)`
----------------------------------------
Share the directory or file at `host_path` with the image where it will be
accessible as `image_path`.

If `image_path` is `None` (the default), then it will be accessible at the
same location in both host and container.

<dl>
<dt><code>host_path</code>:</dt>
<dd>The path on the host system of the directory or file to share.
If it's a relative path, then it's relative to the currently parsed
definition file.
</dd>
<dt><code>image_path</code>:</dt>
<dd>The path in the container where the file or directory will be accessible,
or None to use the same path in both host and container.
Defaults to <code>None</code>.
</dd>
</dl>

`share_path_in_home(relative_path)`
-----------------------------------
Share the directory or file at `relative_path` between host and image.

The path should be relative to the home directory and will be shared in
the image at the same relative path.
By default the paths will be identical because the home directory in the
image and host match, but this can be changed by setting `user_home`.

<dl>
<dt><code>relative_path</code>:</dt>
<dd>The path, relative to the home directory, to share between host and
image.
</dd>
</dl>

`additional_archs`
------------------
A list of additional architectures to support in the image.

This is, for instance, useful to install 32-bit packages on a 64-bit distro.

The only value currently supported is `'i386'` and is supported only on Debian
and Ubuntu.

`architecture`
--------------
The architecture for the image.

Possible values are:

- `x86_64` (default value if you don't specify anything): Also known as x64, x86-64,
  or amd64. This is the normal 64-bit architecture for most computers.
- `armv7`: 32-bit ARMv7.
- `aarch64`: 64-bit ARMv8.

Note that not every distro is supported on every architecture.
In particular, the Docker support for ARM is experimental and may break at any
point (and it actually does, quite often).

`deb_based`
-----------
Whether the currently selected distro is based on Debian (i.e. it's Debian or Ubuntu).

`definition_file_path`
----------------------
The path to the current definition file.

`distro`
--------
The distro used for the image.

This is in the Docker format, i.e. the distro name, a colon and the tag name.
If you don't specify the tag when setting the distro, "latest" is used.

The default distro is `ubuntu:latest`, that is the most recent LTS version
of Ubuntu.

`distro_components`
-------------------
The distro used for the image as a tuple.
The first item is the distro name, the second the tag.

`distro_name`
-------------
The name of the distro without any tag.

`distro_tag`
------------
The tag part of the distro name.

`docker_distro_full_name`
-------------------------
The name of the distro as it will be used in the Dockerfile.

This may be different from `distro` if an architecture was specified.

`hostname`
----------
The hostname for the image.

The default value is `IMAGE_NAME-on-HOST-HOSTNAME`.

`image_home_path_on_host`
-------------------------
The path on the host where to store the content of the non-root user home directory.

By default, the home directory of the non-root user gets saved on the host. This
allows configuration files to persist across invocations.

You should not set this to the host home directory to avoid messing up your
configuration files, for instance if you have different versions of the same
program running on the host and inside the image.

By default, this is set to `~/.karton/home-dirs/IMAGE-NAME`.

`image_name`
------------
The mame of the image.

`packages`
----------
A list of packages to install in the image.

The package names are those used by the distro you are using for the image.

Note that some packages, like `python`, will be installed automatically by
Karton as they are needed for it to work. You should not rely on this and
explicitly install everything you need.

`rpm_based`
-----------
Whether the currently selected distro is based on RPM packages (i.e. it's CentOS or
Fedora).

`sudo`
------
Whether to install the `sudo` command and whether passwordless `sudo` should
be allowed.

Possible values are:

- `DefinitionProperties.SUDO_PASSWORDLESS` (the default):
  install `sudo` and don't require a password.
- `DefinitionProperties.SUDO_WITH_PASSWORD`:
  install `sudo` but require a password.
- `DefinitionProperties.SUDO_NO`:
  don't install `sudo`.

`user_home`
-----------
The path (valid inside the image) of the non-root user home directory.

It's recommended to keep the home directory identical in the host and image.
This helps in case any tool writes an image path into a file which is later
accessed on the host.

`username`
----------
The name of the normal non-root user.

This defaults to the same user name used on the host.
