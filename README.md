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
