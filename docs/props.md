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

`commands_to_run(when)`
-----------------------
Return a list of commands to run at a specific time.

<dl>
<dt><code>when</code>:</dt>
<dd>The time when to run the commands, see <code>run_command</code> for details.
</dd>
</dl>

`copy(src_path, dest_path)`
---------------------------
Copy a file or directory from the host into the image.

All the files will be owned by root.

<dl>
<dt><code>src_path</code>:</dt>
<dd>The path to copy into the image.
It can be an absolute path or a path relative to the current definition file.
</dd>
<dt><code>dest_path</code>:</dt>
<dd>The absolute path in the image where to copy the file or directory.
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
The third is the consistency.
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

`run_command(when, *args)`
--------------------------
Run a shell command at the specified point.

Commands can be run at different stages of the build phase, when running a command, etc:

- `DefinitionProperties.RUN_AT_BUILD_START`:
  during the build phase, before any setup or packages are installed.
- `DefinitionProperties.RUN_AT_BUILD_BEFORE_USER_PKGS`:
  during the build phase, after the base system is setup (including Python), but extra
  packages are not installed yet.
- `DefinitionProperties.RUN_AT_BUILD_END`:
  during the build phase, at the very end of the Dockerfile.
- `DefinitionProperties.RUN_AT_START`:
  when the image is started, i.e. when `karton start IMAGE_NAME` is used or when it's
  automatically started because of `karton run IMAGE_NAME COMMAND ARGS`.
- `DefinitionProperties.RUN_BEFORE_COMMAND`:
  before executing a command, i.e. just before launching `COMMAND ARGS` when doing
  `karton run IMAGE_NAME COMMAND ARGS`.
- `DefinitionProperties.RUN_AFTER_COMMAND`:
  after executing a command, i.e. just after launching `COMMAND ARGS` when doing
  `karton run IMAGE_NAME COMMAND ARGS`.
  Note that this command is executed even if the invoked command failed.
- `DefinitionProperties.RUN_AT_STOP`:
  before stopping an image, i.e. when doing `karton stop IMAGE_NAME`.

Note that, if commands run during the build phase fail (return non-zero), then the build
will abort.
On the other hand, the return code of commands run later is ignored.

<dl>
<dt><code>when</code>:</dt>
<dd>When to run the command.
</dd>
<dt><code>*args</code>:</dt>
<dd>The command to run and its arguments.
</dd>
</dl>

`share_path(host_path, image_path=None, consistency=None)`
----------------------------------------------------------
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
<dt><code>consistency</code>:</dt>
<dd>The consistency level to use to share this path. See <code>default_consistency</code>
for details.
Use <code>None</code> if you want to use the default consistency as set by the
<code>default_consistency</code> property.
This is ignored on Linux.
</dd>
</dl>

`share_path_in_home(relative_path, consistency=None)`
-----------------------------------------------------
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
<dt><code>consistency</code>:</dt>
<dd>The consistency level to use to share this path. See <code>default_consistency</code>
for details.
Use <code>None</code> if you want to use the default consistency as set by the
<code>default_consistency</code> property.
This is ignored on Linux.
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

`copied`
--------
A list of tuples representing the files or directories copied into the image.

The first element of the tuple is the absolute path in the host of the file or
directory; the second is the absolute path in the image.

`deb_based`
-----------
Whether the currently selected distro is based on Debian (i.e. it's Debian or Ubuntu).

`default_consistency`
---------------------
Content shared between images and host need to be kept consistent.
If you modify a file on the host it must be updated also in the image
and vice versa.

On MacOS, if you don't need perfect instant consistency between the
two, you can selected a different level of consistency allowing some
delay in updating either the host or image.
This slight delay allows for increased performances.

On Linux, this option is ignored.

You can select a per-path level of consistency with the `consistency`
argument to `share_path` and `share_path_in_home`.

If you have multiple paths to share, you can specify a default consistency
to use with the `default_consistency` property.

Valid values are:

- `DefinitionProperties.CONSISTENCY_CONSISTENT` (the default):
   perfect consistency, i.e. host and image alway have an identical view
   of the file system content.
- `DefinitionProperties.CONSISTENCY_CACHED`:
   The host's view is authoritative, i.e. updates from the host can be
   delayed before appearing in the image.
- `DefinitionProperties.CONSISTENCY_DELEGATED`:
   The image's view is authoritative, i.e. updates from the image can be
   delayed before appearing in the host.

See the [Docker documentation](https://docs.docker.com/docker-for-mac/osxfs-caching/)
for more details.

`definition_file_dir`
---------------------
The path of the directory containing the current definition file.

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

`share_whole_home`
------------------
Whether the whole host home directory is shared as home directory in the image.

Note that this means that configuration files (like all of your dot-files) modified in
the image will be modified in the host as well.

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

`uid`
-----
The uid of the normal non-root user.

This defaults to the same uid used on the host.

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
