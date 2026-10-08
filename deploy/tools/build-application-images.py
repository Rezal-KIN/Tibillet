#!/usr/bin/env python3
"""Build immutable Lespass, Fedow and LaBoutik candidates in CodeBuild."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from application_images import image_files


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def verify_native_sources(catalog):
    spec = importlib.util.spec_from_file_location('image_source_offer', 'deploy/tools/build-source-offer.py')
    offer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(offer)
    natives = {component: offer.upstream_source(catalog[component], Path('.context/source-cache'))
               for component in ('fedow', 'laboutik')}
    subprocess.run(['python3', 'TECH_DOC/features-enlevees/verify-restored-code.py'],
                   check=True, stdout=subprocess.DEVNULL)
    notice = '# AM-Rezal modified version, imported 2026-09-21; source notices updated 2026-10-03.\n# Original TiBillet authors retained. GNU AGPLv3: see /LICENSE and /NOTICE.md.\n'
    for component, folder, target in (('fedow', 'Fedow', 'fedowallet_django/settings.py'),
                                      ('laboutik', 'Laboutik', 'Cashless/settings.py')):
        source = Path('deploy/' + folder + '/settings.py').read_text().removeprefix(notice)
        if component == 'fedow':
            source = source.replace("'DIRS': [BASE_DIR / 'source_templates'],", "'DIRS': [],")
        else:
            source = source.replace("'DIRS': [os.path.join(BASE_DIR, 'source_templates')],", "'DIRS': [],")
            source = source.replace("EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')\n", '')
            source = source.replace("EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS') == '1'", "EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', False)")
            source = source.replace("EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL') == '1'", "EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', True)")
        if source != natives[component][target][0].decode():
            raise ValueError('settings contain changes outside the agreed email/source-template scope: ' + component)


def main():
    commit = run('git', 'rev-parse', 'HEAD')
    if commit != os.environ['CODEBUILD_RESOLVED_SOURCE_VERSION']:
        raise ValueError('build checkout differs from CodePipeline source revision')
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD'], check=True)
    registry = os.environ['AWS_ACCOUNT_ID'] + '.dkr.ecr.' + os.environ['AWS_DEFAULT_REGION'] + '.amazonaws.com'
    catalog = json.loads(Path('deploy/source/image-sources.json').read_text())
    verify_native_sources(catalog)
    # Only explicit build inputs are read. Runtime data and private CSVs are
    # never copied into the two native application images.
    inputs = run('git', 'ls-files', 'deploy/Fedow', 'deploy/Laboutik', 'deploy/source/admin-templates').splitlines()
    snapshot = {path: (Path(path).read_bytes(), 0o644) for path in inputs if Path(path).suffix in {'.py', '.html'}}
    for folder in ('Fedow', 'Laboutik'):
        path = 'deploy/' + folder + '/Dockerfile'
        if run('git', 'ls-files', path) != path:
            raise ValueError('application Dockerfile must be versioned before building a release')
        snapshot[path] = (Path(path).read_bytes(), 0o644)
    result = {'application_repository': 'Rezal-KIN/Tibillet', 'fork_commit': commit,
              'platform': os.environ['RELEASE_PLATFORM'], 'image_builds': {}}
    for component, dockerfile in (('lespass', 'dockerfile'), ('fedow', 'deploy/Fedow/Dockerfile'), ('laboutik', 'deploy/Laboutik/Dockerfile')):
        repo = os.environ[component.upper() + '_ECR_REPOSITORY']
        base = None
        if component != 'lespass':
            base, _ = image_files(component, snapshot)
            if base != catalog[component]['image']:
                raise ValueError('Dockerfile base differs from audited native image')
        tag = 'sha-' + commit
        ref = registry + '/' + repo + ':' + tag
        lookup = subprocess.run(['aws', 'ecr', 'describe-images', '--repository-name', repo,
                                 '--image-ids', 'imageTag=' + tag, '--query', 'imageDetails[0].imageDigest', '--output', 'text'],
                                capture_output=True, text=True)
        digest = lookup.stdout.strip() if lookup.returncode == 0 else ''
        if not digest or digest == 'None':
            subprocess.run(['docker', 'build', '--platform', 'linux/amd64', '--pull', '--build-arg', 'SOURCE_COMMIT=' + commit,
                            '--tag', ref, '--file', dockerfile, '.'], check=True)
            subprocess.run(['docker', 'push', ref], check=True)
            digest = run('aws', 'ecr', 'describe-images', '--repository-name', repo,
                         '--image-ids', 'imageTag=' + tag, '--query', 'imageDetails[0].imageDigest', '--output', 'text')
        else:
            subprocess.run(['docker', 'pull', ref], check=True)
        if not digest.startswith('sha256:') or len(digest) != 71:
            raise ValueError('ECR did not return a complete image digest')
        if base:
            labels = json.loads(run('docker', 'image', 'inspect', '--format', '{{json .Config.Labels}}', ref))
            if labels.get('org.opencontainers.image.revision') != commit or labels.get('org.opencontainers.image.base.name') != base:
                raise ValueError('existing application image was built from different sources')
            result['image_builds'][component] = {'base_image': base, 'source_commit': commit}
        result[component + '_image'] = registry + '/' + repo + '@' + digest
    Path('release-candidate.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
