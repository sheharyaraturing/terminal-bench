FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Harbor supplies its own agent process. Clear the image's sandbox entrypoint so
# it does not compete. Required — do not remove.
ENTRYPOINT []
CMD ["/bin/bash"]

# No fixtures. This task audits only the data already baked into the base image —
# the eight CSVs under /data and the warehouse at /data/db/turing.db. Nothing is
# copied in and nothing is mutated, so the image is byte-identical to the base and
# task.toml sets docker_image to pull it directly rather than build.
#
# This file exists so that `harbor run --force-build` still yields the same image
# instead of failing on a missing build context. If you add a fixture here, you
# MUST also remove docker_image from task.toml, or harbor's
# should_use_prebuilt_docker_image() will skip this file entirely and your fixture
# will silently not exist at run time.
