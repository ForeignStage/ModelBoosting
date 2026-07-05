# FastAPI Patterns

## HTTPException
```python
from fastapi import HTTPException
raise HTTPException(status_code=404, detail="Item not found")
raise HTTPException(status_code=400, detail="Bad request")
raise HTTPException(status_code=422, detail="Validation error")
raise HTTPException(status_code=500, detail="Internal server error")
```

## Dependency Injection (DB Session)
```python
from fastapi import Depends
from sqlalchemy.orm import Session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/items/{id}")
def get_item(id: int, db: Session = Depends(get_db)):
    ...
```

## Pydantic v2 Model
```python
from pydantic import BaseModel, Field, field_validator

class Item(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., gt=0)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v):
        return v.strip()
```

## Async Endpoint with try/except
```python
@app.post("/items", status_code=201)
async def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    try:
        db_item = Item(**item.model_dump())
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
```

## CORS Middleware
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])
```

## Background Tasks
```python
from fastapi import BackgroundTasks

def send_email(email: str): ...

@app.post("/register")
def register(bg: BackgroundTasks, email: str):
    bg.add_task(send_email, email)
    return {"status": "queued"}
```

## File Upload
```python
from fastapi import UploadFile, File

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    return {"filename": file.filename, "size": len(content)}
```
