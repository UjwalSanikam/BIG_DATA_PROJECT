"""Download HTTPS artifacts with checksum validation before extraction."""
import hashlib, json, pathlib, re, subprocess, urllib.request
root = pathlib.Path(__file__).resolve().parent / 'runtime'
root.mkdir(exist_ok=True)
def read(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()
def install(name, url, digest, algorithm):
    target = root / name
    if target.exists():
        print('Reusing', target)
        return
    archive = root / (name + '.tar.gz')
    print('Downloading', name, flush=True)
    h = hashlib.new(algorithm)
    with urllib.request.urlopen(url, timeout=120) as src, archive.open('wb') as out:
        while block := src.read(1024 * 1024):
            h.update(block)
            out.write(block)
    if h.hexdigest().lower() != digest.lower():
        raise RuntimeError('CHECKSUM FAILED: ' + name)
    staging = root / (name + '.extracting')
    staging.mkdir(exist_ok=True)
    subprocess.run(['tar', '-xzf', str(archive), '--strip-components=1', '-C', str(staging)], check=True)
    staging.rename(target)
    archive.unlink()
    print('Verified', name)
assets = json.loads(read('https://api.adoptium.net/v3/assets/latest/11/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse'))
pkg = assets[0]['binary']['package']
install('java', pkg['link'], pkg['checksum'], 'sha256')
for name, url in [('hadoop', 'https://archive.apache.org/dist/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz'), ('spark', 'https://archive.apache.org/dist/spark/spark-3.5.3/spark-3.5.3-bin-hadoop3.tgz')]:
    digest = re.search(r'\b[0-9a-fA-F]{128}\b', read(url + '.sha512').decode()).group()
    install(name, url, digest, 'sha512')
