FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Clear the image's sandbox entrypoint so it does not compete with harbor's own agent process. Required — do not remove.
ENTRYPOINT []
CMD ["/bin/bash"]

# The repository this task audits, as a bundle not a build-time clone: no network, immune to force-push, and full history — the task turns on 2015 commits and the tags containing them, so a shallow clone gives the agent nothing to find.
COPY fixtures/agate.bundle /tmp/
RUN git clone /tmp/agate.bundle /data/repos/agate && rm /tmp/agate.bundle

# A bundle clone lands detached on the bundle's HEAD, so pin an explicit SHA onto a named branch and give `git log` a starting point that is stable across rollouts.
RUN cd /data/repos/agate && git checkout -b main 7aa490cbc3d965e0a950dd904ea1f9cf5ced013c
