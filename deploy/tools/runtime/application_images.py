"""Small shared contract for the two applications built from native images."""
import re
from pathlib import PurePosixPath

COMPONENTS = ('fedow', 'laboutik')
IMAGE = re.compile(r'^[^\s@]+@sha256:[0-9a-f]{64}$')
COMMIT = re.compile(r'^[0-9a-f]{40}$')


def validate_image_builds(manifest):
    builds = manifest.get('image_builds')
    if builds is None:
        return {}
    if not isinstance(builds, dict) or set(builds) != set(COMPONENTS):
        raise ValueError('image_builds must describe Fedow and LaBoutik together')
    for component, build in builds.items():
        if not isinstance(build, dict) or set(build) != {'base_image', 'source_commit'}:
            raise ValueError('invalid application image source record')
        if not IMAGE.fullmatch(str(build['base_image'])):
            raise ValueError('application base image must be pinned by digest')
        if not COMMIT.fullmatch(str(build['source_commit'])) or build['source_commit'] != manifest.get('fork_commit'):
            raise ValueError('application image sources differ from fork_commit')
    return builds


def image_files(component, snapshot):
    """Read explicit COPYs from the fixed Dockerfile, not the working directory."""
    folder = {'fedow': 'Fedow', 'laboutik': 'Laboutik'}[component]
    prefix = '/home/fedow/Fedow/' if component == 'fedow' else '/DjangoFiles/'
    dockerfile = snapshot['deploy/' + folder + '/Dockerfile'][0].decode()
    bases = re.findall(r'^FROM (\S+)\s*$', dockerfile, re.MULTILINE)
    if len(bases) != 1 or not IMAGE.fullmatch(bases[0]):
        raise ValueError('application Dockerfile must use one audited base digest')
    copies = {}
    for line in dockerfile.splitlines():
        if not line.startswith('COPY '):
            continue
        match = re.fullmatch(r'COPY --chown=\w+:\w+ (\S+) (\S+)', line)
        if not match:
            raise ValueError('unsupported application image COPY; explicit files required')
        origin, target = match.groups()
        if (not origin.startswith(('deploy/' + folder + '/', 'deploy/source/admin-templates/'))
                or '..' in PurePosixPath(origin).parts
                or not target.startswith(prefix) or '..' in PurePosixPath(target).parts):
            raise ValueError('application image COPY is outside its source scope')
        relative = target[len(prefix):]
        if relative in copies.values():
            raise ValueError('duplicate application image destination')
        if PurePosixPath(relative).suffix not in {'.py', '.html'}:
            raise ValueError('only audited Python and HTML sources may be copied')
        snapshot[origin]  # Missing/unversioned sources stop the build or publication.
        copies[origin] = relative
    if not copies:
        raise ValueError('application image has no explicit source files')
    return bases[0], copies
