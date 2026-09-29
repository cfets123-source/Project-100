from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def initialize_schema(target_engine=engine):
    """Serialize SQLite schema creation with worker startup; no data deletion."""
    with target_engine.connect() as conn:
        if target_engine.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        Base.metadata.create_all(bind=conn)
        # Additive migration for the development-era defensive-intent table.
        # No existing order, halt or account data is deleted or reset.
        columns = {c['name'] for c in inspect(conn).get_columns('defensive_order_intents')}
        for name, declaration in (
            ('entry_order_id', 'VARCHAR'), ('filled_quantity', 'FLOAT NOT NULL DEFAULT 0'),
            ('fill_price', 'FLOAT')):
            if name not in columns:
                conn.exec_driver_sql(f'ALTER TABLE defensive_order_intents ADD COLUMN {name} {declaration}')
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
