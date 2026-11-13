"""Validate the generated environment file before Bash sources it."""
import ipaddress, pathlib, re, sys

def validate(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if not re.fullmatch(r'(NODE|N[1-4]|LAB_USER|N4_USER)=[a-zA-Z0-9_.-]+', line):
            raise ValueError('Invalid searchlab.env line. Rerun Step 4; do not edit setup.sh.')
        key, value = line.split('=', 1)
        if key in values:
            raise ValueError(f'Duplicate {key} in searchlab.env. Rerun Step 4.')
        values[key] = value
    if values.get('NODE') not in ('1', '2', '3', '4'):
        raise ValueError('NODE must be the number 1, 2, 3 or 4, never a username. Rerun Step 4 for your VM.')
    ips = [str(ipaddress.IPv4Address(values.get(f'N{n}', ''))) for n in range(1, 5)]
    if len(set(ips)) != 4:
        raise ValueError('All four VM IP addresses must be distinct.')
    for key in ('LAB_USER', 'N4_USER'):
        if key in values and not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', values[key]):
            raise ValueError(f'{key} must be a Linux username. Rerun Step 4.')
    return values

if __name__ == '__main__':
    try:
        values = validate(pathlib.Path(sys.argv[1]).read_text())
        print('CONFIG_OK Node', values['NODE'])
    except (ValueError, OSError, IndexError) as exc:
        sys.exit('CONFIG_ERROR: ' + str(exc))
