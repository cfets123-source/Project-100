"""Allow service helpers to participate in an explicitly owned transaction."""


def persist(db):
    if db.info.get("transaction_owner"):
        db.flush()
    else:
        db.commit()
