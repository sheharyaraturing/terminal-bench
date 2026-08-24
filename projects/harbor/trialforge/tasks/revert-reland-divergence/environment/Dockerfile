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
# GIT_COMMITTER_DATE on every commit, so every object SHA is reproducible.
# The bundle was created with `git bundle create ... --all` and carries FULL
# history — never --depth 1, because git_git_log needs it, and because --all is
# what carries refs/tags/* and the UNMERGED hotfix branch. Both matter: two of
# the tags are annotated, one is not a version number at all, and the 1.9.1
# release lives only on a branch that HEAD cannot reach.

COPY fixtures/pipeline-svc.bundle /tmp/
RUN mkdir -p /data/repos \
 && git clone /tmp/pipeline-svc.bundle /data/repos/pipeline-svc \
 && rm /tmp/pipeline-svc.bundle

# Pin the branch tip explicitly. -B rather than -b because the bundle carries
# HEAD, so the clone already has a `main`; -B makes the pin idempotent and
# asserts the SHA either way. Without an explicit branch a bundle clone can land
# detached, and the git server's tooling reads much worse from a detached HEAD.
# The commit-to-release mapping is intentionally NOT flattened here: the tags
# come along with the bundle and there is no git_tag tool on the git server.
RUN cd /data/repos/pipeline-svc \
 && git checkout -B main aa86ca39961cd50b84023a9002fc38a6ac1054ba \
 && git remote remove origin \
 && git config user.name  "pipeline-svc build" \
 && git config user.email "build@example.invalid"

# Fail the build rather than ship a repository that is not the one the claims
# describe. `git cat-file -t <SHA>` is the check the conventions ask for.
RUN cd /data/repos/pipeline-svc \
 && test "$(git cat-file -t aa86ca39961cd50b84023a9002fc38a6ac1054ba)" = "commit" \
 && test "$(git rev-parse HEAD)" = "aa86ca39961cd50b84023a9002fc38a6ac1054ba" \
 && test "$(git rev-parse --abbrev-ref HEAD)" = "main" \
 && test "$(git rev-list --count HEAD)" = "56" \
 && test "$(git rev-list --count --merges HEAD)" = "1" \
 && test "$(git rev-list --count --all)" = "59" \
 && test "$(git tag | wc -l)" = "10" \
 && test "$(git cat-file -t refs/tags/v1.10.0)" = "tag" \
 && test -f src/backoff.py \
 && test -s CHANGELOG.md
