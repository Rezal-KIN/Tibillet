#!/usr/bin/env python3
"""Reject an unbuilt application or mismatched source labels before startup."""
import json
import subprocess
import sys
from application_images import COMPONENTS, validate_image_builds


def main():
    with open(sys.argv[1]) as stream:
        manifest = json.load(stream)
    builds = validate_image_builds(manifest)
    if not builds:
        raise ValueError('this release requires Fedow and LaBoutik images from the new Test build')
    for component in COMPONENTS:
        result = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{json .Config.Labels}}',
                                          manifest[component + '_image']], text=True)
        labels = json.loads(result) or {}
        build = builds[component]
        if (labels.get('org.opencontainers.image.revision') != build['source_commit']
                or labels.get('org.opencontainers.image.base.name') != build['base_image']):
            raise ValueError('application image labels differ from the release source record: ' + component)
    print('Application images match their fixed source revision and native bases')


if __name__ == '__main__':
    main()
