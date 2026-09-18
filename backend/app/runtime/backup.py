"""SQLite online backup/restore copy. Refuses to overwrite any destination."""
import argparse
from pathlib import Path
import sqlite3


def copy_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError('source database does not exist')
    if source == destination:
        raise ValueError('source and destination must differ')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Atomic exclusive creation avoids accidentally overwriting a running DB.
    with destination.open('xb'):
        pass
    try:
        with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('backup integrity check failed')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = copy_database(args.source, args.destination)
    print(f'Integrity-checked SQLite copy saved: {result}')


if __name__ == '__main__':
    main()
