# Publishing ALMOS to PyPI

`check-pr-version` runs on pull requests into `master` and compares `ALMOS_VERSION` in
`almos/package_versions.py` with the current version on `master`. Any strictly higher
public PEP 440 version passes, including a patch release. Set the version you want to
publish in the PR.

`publish-to-pypi` runs on pushes to `master` after `build-and-test` and
`codecov-coverage` succeed. It checks that `ALMOS_VERSION` is higher than every version
of `almos-kit` on PyPI, builds a source distribution and wheel, checks both with Twine,
and uploads them. An unavailable PyPI version check or a missing token fails the job.

## One-time setup

1. In CircleCI **Project Settings → Project Setup**, configure a GitHub App pipeline
   for ALMOS with the **PR opened or pushed to, default branch and tag pushes** trigger.
   This trigger sends `master` pushes when `master` is GitHub's default branch.
2. In PyPI **Account settings → API tokens**, create a token scoped to `almos-kit`.
3. In CircleCI **Organization Settings → Contexts**, create `almos-pypi-publish`,
   restrict it to the ALMOS project, and add the token as `ALMOS_PYPI_TOKEN`,
   including its `pypi-` prefix. Use this expression restriction so only a
   GitHub App push that builds `master` with its own config can access the token.

   ```text
   pipeline.integration_source == "github_app"
   and pipeline.event.name == "push"
   and pipeline.event.github.ref == "refs/heads/master"
   and pipeline.config.ref == "refs/heads/master"
   and pipeline.git.branch == "master"
   and not job.ssh.enabled
   ```

4. After the first PR reports `check-pr-version`, require that check in GitHub's
   branch protection or ruleset for `master`. Require branches to be up to date
   before merging so the check reruns if `master` advances.

CircleCI's GitHub App triggers pull request pipelines for branches in the ALMOS
repository. For a contribution from a fork, review the changes and open a PR
from a branch in the ALMOS repository so CircleCI can report the required check.
