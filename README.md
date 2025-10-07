# Budget App Project

---

## Setting up Database

After downloading Docker pull down a postgres image
```zsh
docker pull postgres
```

---

Then create a database with a volume
```zsh
docker run --name budget-app-db \
  -e POSTGRES_DB=budget_app \
  -e POSTGRES_PASSWORD=pass123 \
  -e POSTGRES_USER=user \
  -p 5434:5432 \
  -v budget-app-data:/var/lib/postgresql/data \
  -d postgres
```

---

## Running the API

Install dependencies and run the FastAPI app (example using uvicorn):
```zsh
pip install fastapi uvicorn sqlalchemy python-dotenv psycopg2-binary
uvicorn app.main:app --reload
```

Ensure you have a .env file with DATABASE_URL, e.g.:
```
DATABASE_URL=postgresql+psycopg2://user:pass123@localhost:5434/budget_app
```

---

## Categories API

- Create category
  - POST /categories/
  - Body: { "name": "Groceries", "parent_id": null }

- List categories (optionally by parent)
  - GET /categories/?parent_id=<uuid>

- Read category by id
  - GET /categories/{category_id}

- Update category
  - PUT /categories/{category_id}
  - Body: { "name": "New Name", "parent_id": "<uuid or null>" }

- Delete category
  - DELETE /categories/{category_id}
  - Returns 204 No Content on success