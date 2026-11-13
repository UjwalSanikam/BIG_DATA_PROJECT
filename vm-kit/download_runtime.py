"""Pinned downloads with verification, retry, and non-destructive recovery."""
import hashlib, json, pathlib, subprocess, tempfile, time, urllib.error, urllib.request, uuid
ROOT = pathlib.Path(__file__).resolve().parent / 'runtime'
# Digests published by the official release owners; no live API lookups.
ARTIFACTS = {
 'python311': ('https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.11.18%2B20261026-x86_64-unknown-linux-gnu-install_only.tar.gz', 'a87ee63646c8f8438b7af3954b2135ed2af91d033c631f12a8f20af903046d06', 'sha256', 'bin/python3.11'),
 'java': ('https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.33%2B10/OpenJDK11U-jdk_x64_linux_hotspot_11.0.33_10.tar.gz', 'c4b8eaf56c93b95b689ffc08d155df1bcdbbffb666f8f71d21d97aedaea6f0ec', 'sha256', 'bin/java'),
 'hadoop': ('https://archive.apache.org/dist/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz', 'de3eaca2e0517e4b569a88b63c89fae19cb8ac6c01ff990f1ff8f0cc0f3128c8e8a23db01577ca562a0e0bb1b4a3889f8c74384e609cd55e537aada3dcaa9f8a', 'sha512', 'bin/hdfs'),
 'spark': ('https://archive.apache.org/dist/spark/spark-3.5.3/spark-3.5.3-bin-hadoop3.tgz', '3b041e538282c15ad3b0ab2f05d558e1be2d16e047c2a98ca9c08176c4a50e7101bd2199aec97a66fdabf4b3f490c2c1cefd547bbe35a1b3e3143e066948ee6d', 'sha512', 'bin/spark-submit'),
}

def download(url, archive, digest, algorithm):
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SearchLab/1.1'})
            h, total, next_report = hashlib.new(algorithm), 0, 32 * 1024 * 1024
            with urllib.request.urlopen(req, timeout=120) as src, archive.open('wb') as out:
                while block := src.read(1024 * 1024):
                    h.update(block)
                    out.write(block)
                    total += len(block)
                    if total >= next_report:
                        print(f'  Downloaded {total // (1024 * 1024)} MiB', flush=True)
                        next_report += 32 * 1024 * 1024
            if h.hexdigest().lower() != digest.lower():
                raise RuntimeError('CHECKSUM_FAILED: file does not match the pinned release; it will not be extracted.')
            return
        except (OSError, urllib.error.URLError) as exc:
            if attempt == 3 or isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404):
                raise RuntimeError(f'DOWNLOAD_FAILED: {url}\n{exc}\nCheck VM internet access to this host. Keep TLS and checksum checks enabled. Retry after fixing connectivity.') from exc
            print(f'Download interrupted; retry {attempt}/3: {exc}', flush=True)
            time.sleep(attempt * 2)

def install(name, root=ROOT):
    url, digest, algorithm, required = ARTIFACTS[name]
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    marker = target / '.searchlab-download.json'
    expected = {'url': url, 'digest': digest}
    try:
        if json.loads(marker.read_text()) == expected and (target / required).is_file():
            print('Reusing verified', name, flush=True)
            return target
    except (OSError, ValueError):
        pass
    legacy = {'hadoop': 'share/hadoop/common/hadoop-common-3.3.6.jar', 'spark': 'jars/spark-core_2.12-3.5.3.jar'}
    if name in legacy and (target / required).is_file() and (target / legacy[name]).is_file():
        print('Reusing existing', name, '(version checked again by doctor)', flush=True)
        return target
    archive = root / (name + '.partial')
    print('Downloading', name, 'from', url, flush=True)
    download(url, archive, digest, algorithm)
    with tempfile.TemporaryDirectory(prefix=name + '.extracting-', dir=root) as temp:
        staging = pathlib.Path(temp)
        subprocess.run(['tar', '-xzf', str(archive), '--strip-components=1', '-C', str(staging)], check=True)
        if not (staging / required).is_file():
            raise RuntimeError(f'EXTRACTION_FAILED: {required} is missing; existing installation is unchanged.')
        (staging / '.searchlab-download.json').write_text(json.dumps(expected))
        backup = None
        if target.exists():
            backup = root / (name + '.previous-' + uuid.uuid4().hex[:8])
            target.rename(backup)
            print('Preserved previous installation at', backup, flush=True)
        try:
            staging.rename(target)
        except OSError:
            if backup and not target.exists():
                backup.rename(target)
            raise
    archive.unlink()
    print('Verified', name, flush=True)
    return target

if __name__ == '__main__':
    for name in ('java', 'hadoop', 'spark'):
        install(name)
