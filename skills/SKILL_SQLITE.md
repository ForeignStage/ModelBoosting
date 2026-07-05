# SKILL: SQLite/SQLAlchemy — Actionable Patterns

## Session setup
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

engine = create_engine("sqlite:///state.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase): pass
```

## Model definition
```python
from sqlalchemy import Column, Integer, String, DateTime, func
class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
```

## CRUD patterns
```python
# Create
db.add(Item(name="x")); db.commit(); db.refresh(item)

# Read
item = db.query(Item).filter(Item.id == id).first()
items = db.query(Item).filter(Item.name.like("%q%")).all()

# Update
db.query(Item).filter(Item.id == id).update({"name": "y"}); db.commit()

# Delete
db.query(Item).filter(Item.id == id).delete(); db.commit()
```

## Transaction with rollback
```python
try:
    db.add(obj); db.commit()
except Exception:
    db.rollback(); raise
```

## Raw SQL (when ORM too slow)
```python
from sqlalchemy import text
result = db.execute(text("SELECT * FROM items WHERE id = :id"), {"id": 1})
rows = result.fetchall()
```

## Migration (Alembic one-liner)
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Check table exists (no-ORM bootstrap)
```python
import sqlite3
conn = sqlite3.connect("state.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
```

## RULES
- Always rollback on exception — never leave open transactions
- Use `check_same_thread=False` for SQLite + async/threading
- Prefer ORM for CRUD, raw SQL only for complex aggregations
- `db.refresh(obj)` after commit to get server-generated values
