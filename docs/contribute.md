Contributing to Karton
======================

How does it work?
-----------------

* Karton stores its general configuration in `~/.karton/karton.cfg` and the image-specific configuration in `~/.karton/images/`.
    * `karton.cfg` is a `.ini`-like file.
    * Image configuration files are JSON files.

* Karton uses Docker internally by converting Karton's definitions into `Dockerfile` files.
    * Some configuration properties defined in the `definiton.py` files cannot be used in a `Dockerfile`, so they are stored in the JSON configuration file and applied when the image is started.
    * The `karton build` command calls the `docker build` command to build an image.
* Every Karton image corresponds to a Docker image with the same name.
* While Docker can have multiple containers running for the same image, Karton keeps at most one.
    * For this reason, in Karton we only talk about images and don't mention containers.
    * If you need to talk about a container in the sense of a running image, just say “running image”.
    * If you really need to mention containers (for instance in a Docker-related error message or in verbose logging), say “Docker container”.
* Images are started automatically when a command which needs an image is used (like `run` and `shell`).
    * You can manually start/stop images using `start` and `stop` but this should rarely be used by users.
* To start an image:
    * The `docker run` command is used to execute `karton/container-code/session_runner.py` (which is copied into the image).
    * Some settings which were not applied at build time (like the list of shared directories) are passed through the `docker run` command.
    * `session_runner.py` keeps the Docker container running and nothing more.
* When a command needs to be executed in the image:
    * The `docker exec` command is used to execute `karton/container-code/command_runner.py` (which is copied into the image).
    * The `command_runner.py` script does some set up and the executes the actual command.


Modifying Karton
----------------

* Karton is written in pure Python (supporting both Python 2.7 and Python 3).
* Most of the code is in the `karton` directory.
    * The `karton/container-code/` directory contains scripts which are copied into the image at build time.
    * The code is, more or less, PEP-8 compliant.
* `scripts/karton` is the main entry point of the program.
* `scripts` contains various useful scripts (written in a mix of bash and Python) which are needed only at build time (with the exception of `scripts/karton`).
* `Makefile` is used to make dist tarballs, run tests, build the logos, etc.
* `tests` contains the tests.
* `inception ` contains code used to run the tests inside a Docker container.

Before submitting any change:

* Check the code with `make lint`.
* Run the tests (see the next section).


Running the tests
-----------------

The tests use the `unittest` module and live in the `tests` directory. These run on your OS and test various aspects of the program.<br>
To add a new test suite or change how tests are run, see `tests/run.py`.

As I use macOS, I need to run tests on Linux as well, ideally on multiple distros. For this, I use various Docker containers which are managed by the code in `inception/`.

There are different ways of running subsets of tests:

* `make check`: Only local tests using Python 2.
* `make check-python-all`: Only local tests, both using Python 2 and 3.
* `make check-inception`: All the inception tests (run in Docker containers).
* `make distcheck`: The full set of local and inception tests.
* `make distcheck-fast`: A subset of local and inception tests which are faster to run than a full `make distcheck`.
* `./tests/run.py test_run.RunTestCase.test_armv7`: Run only the specified test locally.
* `make check-inception TARGETS="debian:latest" TESTS="test_run.RunTestCase.test_armv7"`: Run only the specified test only on `debian-latest`.

Note that tests can take a long time the first time you run them as they need to create a lot of Docker images. Following runs are much much faster.

Running the full set of tests (`make distcheck`) will take a very long time (first run only) and a lot of disk space!


Making a release
----------------

Most of the release process is automated:

1. Install GitHub's [hub tool](https://github.com/github/hub) and make sure it's in your `$PATH`.
2. Check everything looks good.
3. Make sure the main repo is called `origin`.
4. Run `./scripts/release.py prepare` and follow the instructions.
5. Run `make distcheck` and everything else that the previous command told you to do.
6. Run `./scripts/release.py push` and follow the instructions.
7. Make a pip release following the instructions given by the previous command.
