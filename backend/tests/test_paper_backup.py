import pytest
from sqlalchemy import create_engine
from app.core.config import Settings
from app.runtime.paper import PaperRuntime
from app.runtime.backup import copy_database


def test_backup_restores_open_position_and_protection(tmp_path):
    source, backup, restored = [tmp_path/name for name in ('source.db','backup.db','restored.db')]
    cfg = Settings(_env_file=None, AUTO_EXECUTION=True, AUTONOMY_LEVEL=2)
    engine = create_engine(f'sqlite:///{source}')
    rt = PaperRuntime(engine, cfg)
    rt.enable()
    rt.process(dict(event_id='entry', sequence=1, prices={'TST':9.5}, reference_prices={'TST':10}))
    copy_database(source, backup)
    copy_database(backup, restored)
    recovered_engine = create_engine(f'sqlite:///{restored}')
    recovered = PaperRuntime(recovered_engine, cfg)
    assert recovered.status()['positions'] == rt.status()['positions']
    assert recovered.process(dict(event_id='exit',sequence=2,prices={'TST':8.9}))['closed_symbols'] == ['TST']
    assert 'TST' in rt.status()['positions']  # source not changed by restore
    engine.dispose()
    recovered_engine.dispose()


def test_backup_refuses_existing_destination_without_modifying_it(tmp_path):
    src, dst = tmp_path/'source.db', tmp_path/'existing.db'
    src.write_bytes(b'not-a-db')
    dst.write_bytes(b'keep-this')
    with pytest.raises(FileExistsError):
        copy_database(src, dst)
    assert dst.read_bytes() == b'keep-this'
    with pytest.raises(Exception):
        copy_database(src, tmp_path/'failed.db')
    assert not (tmp_path/'failed.db').exists()
