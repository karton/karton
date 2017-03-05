DefinitionProperties
====================

Instructions on how to generate the image and what to include in it.


`abspath(...)`
------------------------------
Make `path` absolute (relative for the currently parsed definition file).

<dl>
<dt><code>path</code>:</dt>
<dd>The path to make absolute if it's relative.
If already absolute, the path is not changed.
</dd>
<dt>Return value:</dt>
<dd>An absolute path.
</dd>
</dl>

`distro_tag(...)`
------------------------------
The tag part of the distro name.

`eval(...)`
------------------------------
Replace variables in `in_string` and return the new string.

FIXME: Document the variable syntanx and valid variables.

`get_path_mappings(...)`
------------------------------
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

`import_definition(...)`
------------------------------
Import an existing definition file.

<dl>
<dt><code>other_definition_directory</code>:</dt>
<dd>The path of the directory where the definition file is.
It can be an absolute path or a path relative to the current definition file.
</dd>
</dl>

`share_path(...)`
------------------------------
Share the directory or file at `host_path` with the image where it will be accessible
as `image_path`.

If `image_path` is None, then it will be accessible at the same location in both host
and container.

<dl>
<dt><code>host_path</code>:</dt>
<dd>The path on the host system of the directory or file to share.
If it's a relative path, then it's relative to the currently parse definition
file.
</dd>
<dt><code>image_path</code>:</dt>
<dd>The path in the container where the file or directory will be accessible,
or None to use the same path in both host and container.
</dd>
</dl>

`share_path_in_home(...)`
------------------------------
Share the directory or file at `relative_path` between host and image.

<dl>
<dt><code>relative_path</code>:</dt>
<dd>The path to share at the same location in both host and image.
The path must a subdirectory of the home directory and relative to it.
</dd>
</dl>

`additional_archs`
------------------------------

`architecture`
------------------------------
The architecture for the image.

`deb_based`
------------------------------
Whether the currently selected distro is based on Debian (i.e. it's Debian or Ubuntu).

`definition_file_path`
------------------------------
The path to the current definition file.

`distro`
------------------------------
The distro used for the image.

This is in the Docker format, i.e. the distro name, a colon and the tag name.
If you don't specify the tag when setting the distro, "latest" is used.

`distro_components`
------------------------------
The distro used for the image, split into the distro name and the tag.

`distro_name`
------------------------------
The name of the distro without any tag.

`docker_distro_full_name`
------------------------------
The name of the distro to use in the Dockerfile.

This may be different from `DefinitionProperties.distro` if an architecture was
specified.

`hostname`
------------------------------
The hostname for the image.

The default value is "IMAGE_NAME-on-HOST-HOSTNAME".

`image_home_path_on_host`
------------------------------
The path on the host where to store the content of the home directory from the
image.

You should not set this to the host home directory to avoid messing up your
configuration files.

`image_name`
------------------------------
The mame of the image.

`packages`
------------------------------

`rpm_based`
------------------------------
Whether the currently selected distro is based on RPM packages (i.e. it's CentOS or
Fedora).

`sudo`
------------------------------

`user_home`
------------------------------
The path (valid inside the image) of the normal non-root user home directory.

It's recommended to keep the home directory identical in the host and image.
This helps in case any tool write an image path into a file which is later
accessed on the host.

`username`
------------------------------
The name of the normal non-root user.

