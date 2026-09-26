// Fork publisher, following the same immutable-wheel pattern as the
// organization's other driver forks. PR wheels carry a PEP 440 local version
// (<version>+pr.<number>.<revision>, normalized by ci/release_version.py);
// stable wheels are published only from reviewed master. An existing
// artifact is never overwritten.
podTemplate(
    imagePullSecrets: ['preset-pull'],
    containers: [
        containerTemplate(name: 'ci', image: 'preset/ci:latest',
            ttyEnabled: true, command: 'cat'),
        containerTemplate(name: 'py-ci', image: 'preset/python:3.9.18-2024-02-21-ci',
            ttyEnabled: true, command: 'cat')
    ]
) {
    node(POD_LABEL) {
        checkout scm
        def revision = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
        boolean isMaster = env.BRANCH_NAME == 'master'
        boolean isPR = env.CHANGE_ID != null
        if (!isMaster && !isPR) {
            error('Only master and pull-request builds publish; use a PR.')
        }
        def version = ''
        def wheel = ''

        container('py-ci') {
            stage('Test and build') {
                withEnv(["CHANGE_NUMBER=${isPR ? env.CHANGE_ID : ''}", "REVISION=${revision.take(12)}"]) {
                    sh '''
                        set -eu
                        python -m venv .venv
                        .venv/bin/pip install 'sqlalchemy==2.0.52' 'pytest==7.4.4' 'pytest-mock==3.14.0' \
                            'boto3>=1.36,<2' 'packaging==24.2' 'build==1.4.4' 'setuptools==80.9.0' 'wheel==0.45.1'
                        .venv/bin/pip install --no-deps .
                        .venv/bin/python -m pytest -q tests
                        BASE_VERSION=$(.venv/bin/python -c "import re; print(re.search(r\\"^__version__ = '([^']*)'\\", open('kylinpy/__init__.py').read(), re.M).group(1))")
                        .venv/bin/python ci/release_version.py "$BASE_VERSION" "$CHANGE_NUMBER" "$REVISION" > release.version
                    '''
                }
                version = readFile('release.version').trim()
                wheel = "kylinpy-${version}-py3-none-any.whl"
                withEnv(["PUBLISH_VERSION=${version}", "WHEEL=${wheel}"]) {
                    sh '''
                        set -eu
                        .venv/bin/python - <<'PY'
import os
import re
from pathlib import Path
path = Path('kylinpy/__init__.py')
lines = path.read_text().splitlines(keepends=True)
assert sum(line.startswith('__version__ = ') for line in lines) == 1
path.write_text(''.join('__version__ = ' + repr(os.environ['PUBLISH_VERSION']) + '\\n'
                        if line.startswith('__version__ = ') else line for line in lines))
PY
                        SOURCE_DATE_EPOCH=$(git -c safe.directory="$PWD" log -1 --format=%ct)
                        case "$SOURCE_DATE_EPOCH" in
                            ''|*[!0-9]*) echo "Invalid commit timestamp for reproducible build" >&2; exit 1 ;;
                        esac
                        export SOURCE_DATE_EPOCH
                        # Pin the build backend and remove stale output for reproducible retries.
                        rm -rf build dist kylinpy.egg-info
                        .venv/bin/python -m build --wheel --no-isolation
                        test -f "dist/$WHEEL" || { echo "missing dist/$WHEEL"; ls -1 dist; exit 1; }
                        test "$(ls -1 dist | wc -l)" -eq 1 || { echo "unexpected dist contents"; ls -1 dist; exit 1; }
                        if .venv/bin/python -m zipfile -l "dist/$WHEEL" | awk '{print $1}' | grep -q '^tests/'; then
                            echo "wheel must not ship the tests package"; exit 1
                        fi
                        .venv/bin/pip install --force-reinstall --no-deps "dist/$WHEEL"
                        .venv/bin/python - <<'PY'
import importlib.metadata as im
import os
import sqlalchemy as sa
from sqlalchemy.sql import compiler
before = set(compiler.IdentifierPreparer.reserved_words)
assert im.version('kylinpy') == os.environ['PUBLISH_VERSION']
engine = sa.create_engine('kylin://user:pass@localhost:7070/project')
assert engine.dialect.name == 'kylin'
assert set(compiler.IdentifierPreparer.reserved_words) == before
engine.dispose()
PY
                    '''
                }
            }
        }
        container('ci') {
            stage('Publish immutable wheel') {
                withCredentials([[
                    $class: 'AmazonWebServicesCredentialsBinding',
                    credentialsId: 'ci-user',
                    accessKeyVariable: 'AWS_ACCESS_KEY_ID',
                    secretKeyVariable: 'AWS_SECRET_ACCESS_KEY'
                ]]) {
                    withEnv(["WHEEL=${wheel}", "KEY=kylinpy/${wheel}",
                             "ALLOW_IDENTICAL_PR_ARTIFACT=${isPR && !isMaster}"]) {
                        sh '''
                            set -eu
                            python -m pip install --quiet 'boto3>=1.36,<2'
                            python ci/publish_wheel.py
                        '''
                    }
                }
            }
        }
        archiveArtifacts artifacts: 'dist/*.whl,published.sha256', fingerprint: true
    }
}
