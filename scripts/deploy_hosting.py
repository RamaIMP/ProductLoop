"""Publish only the two configured dist folders using short-lived gcloud credentials.

Run from the repository root after building both frontends. No private key files.
"""
import gzip
import hashlib
import json
from pathlib import Path
import ssl
import subprocess
import urllib.request
from urllib.parse import urlparse


def main():
    root = Path(__file__).resolve().parents[1]
    rc = json.loads((root / '.firebaserc').read_text())
    project = rc['projects']['default']
    targets = rc['targets'][project]['hosting']
    token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], text=True).strip()
    context = ssl.create_default_context()
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    base = 'https://firebasehosting.googleapis.com/v1beta1/'

    def call(method, url, payload=None, binary=None):
        if urlparse(url).hostname not in {'firebasehosting.googleapis.com', 'upload-firebasehosting.googleapis.com'}:
            raise ValueError('Unexpected deployment API destination')
        body = binary if binary is not None else json.dumps(payload).encode() if payload is not None else None
        headers = {'Authorization': 'Bearer ' + token, 'x-goog-user-project': project,
                   'Content-Type': 'application/octet-stream' if binary is not None else 'application/json'}
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method),
                                    context=context, timeout=120) as response:
            data = response.read()
            return json.loads(data) if data and 'application/json' in response.headers.get('Content-Type', '') else {}

    # Validate both artifacts before creating any Hosting version.
    artifacts = []
    for app, target in [('consumer', 'consumer'), ('dashboard', 'dashboard')]:
        folder = root / 'frontend' / app / 'dist'
        if not (folder / 'index.html').is_file():
            raise RuntimeError('Build both frontends first')
        files, blobs = {}, {}
        for file in sorted(folder.rglob('*')):
            if not file.is_file():
                continue
            relative = file.relative_to(folder)
            if file.is_symlink() or any(part.startswith('.') for part in relative.parts):
                raise RuntimeError('Unexpected hidden file or symlink in build output')
            compressed = gzip.compress(file.read_bytes(), mtime=0)
            digest = hashlib.sha256(compressed).hexdigest()
            files['/' + relative.as_posix()] = digest
            blobs[digest] = compressed
        artifacts.append((targets[target][0], files, blobs))

    for site, files, blobs in artifacts:
        version = call('POST', base + f'sites/{site}/versions', {'config': {
            'rewrites': [{'glob': '**', 'path': '/index.html'}],
            'headers': [{'glob': '**', 'headers': {'Cache-Control': 'no-cache',
                         'X-Content-Type-Options': 'nosniff'}}]}})['name']
        for start in range(0, len(files), 1000):
            batch = dict(list(files.items())[start:start + 1000])
            upload = call('POST', base + version + ':populateFiles', {'files': batch})
            for digest in upload.get('uploadRequiredHashes', []):
                call('POST', upload['uploadUrl'] + '/' + digest, binary=blobs[digest])
        call('PATCH', base + version + '?update_mask=status', {'status': 'FINALIZED'})
        release = call('POST', base + f'sites/{site}/releases?versionName={version}', {})
        print(json.dumps({'site': site, 'release': release['name'], 'url': f'https://{site}.web.app'}), flush=True)


if __name__ == '__main__':
    main()
