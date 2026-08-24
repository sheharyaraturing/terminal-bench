FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Harbor supplies its own agent process. Clear the image's sandbox entrypoint so
# it does not compete. Required — do not remove.
ENTRYPOINT []
CMD ["/bin/bash"]

# ── Fixture ───────────────────────────────────────────────────────────────────
# environment/ is the Docker build context, so everything under fixtures/ can be
# COPYd. This is a normal host build, not docker-in-docker.
#
# task.toml deliberately carries NO docker_image key: if it did, harbor would
# pull the prebuilt image and skip this file, and the repository below — which is
# the entire subject of the task — would not exist at run time.
#
# The bundle is produced by fixtures/build_fixture.sh, which pins author name,
# author email, committer name, committer email and BOTH GIT_AUTHOR_DATE and
# GIT_COMMITTER_DATE on every commit, and uses lightweight tags, so every SHA is
# reproducible. A rebuild in an empty directory was verified to reproduce the
# bundle's sha256 exactly. The bundle was created with
# `git bundle create ... --all` and carries FULL history — never --depth 1,
# because git_git_log needs it and this task is entirely about history.

COPY fixtures/metrics-etl.bundle /tmp/
RUN mkdir -p /data/repos \
 && git clone /tmp/metrics-etl.bundle /data/repos/metrics-etl \
 && rm /tmp/metrics-etl.bundle

# Pin the branch tip explicitly. -B rather than -b because the bundle carries
# HEAD, so the clone already has a `main`; -B makes the pin idempotent and
# asserts the SHA either way. Without an explicit branch a bundle clone can land
# detached, and the git server's tooling reads much worse from a detached HEAD.
# The commit-to-release mapping is intentionally NOT flattened here: the eight
# tags come along with the bundle and there is no git_tag tool on the git server,
# so the tag set has to be reached through the code executor.
RUN cd /data/repos/metrics-etl \
 && git checkout -B main 6d120f7400623a25d7d5e08ff0b2dff101bf130b \
 && git remote remove origin \
 && git config user.name  "metrics-etl build" \
 && git config user.email "build@example.invalid"

# Fail the build rather than ship a repository that is not the one the claims
# describe. `git cat-file -t <SHA>` is the check the conventions ask for; the
# rest assert the facts tests/reward.toml depends on.
RUN cd /data/repos/metrics-etl \
 && test "$(git cat-file -t 6d120f7400623a25d7d5e08ff0b2dff101bf130b)" = "commit" \
 && test "$(git rev-parse HEAD)" = "6d120f7400623a25d7d5e08ff0b2dff101bf130b" \
 && test "$(git rev-parse --abbrev-ref HEAD)" = "main" \
 && test "$(git rev-list --count HEAD)" = "52" \
 && test "$(git rev-list --count --merges HEAD)" = "0" \
 && test "$(git tag | wc -l)" = "8" \
 && test "$(git ls-files | wc -l)" = "12" \
 && test -s CHANGELOG.md \
 && test -s build/sbom.txt \
 && test ! -e requirements.lock \
 && git cat-file -e v2.8.0:requirements.lock \
 && test "$(git show v2.9.0:build/sbom.txt  | grep -c '^botocore==1.34.88$')" = "1" \
 && test "$(git show v2.10.0:build/sbom.txt | grep -c '^botocore==1.35.14$')" = "1"
