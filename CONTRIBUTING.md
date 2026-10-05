# Contributing to EV Charging Network

Thank you for contributing to this project! This document outlines the workflow and guidelines for team members.

---

## Team Structure

| Person | Role | Branch | Responsibilities |
|--------|------|--------|------------------|
| Person 1 | Database Architect | `database-schema` | MySQL schema, normalization, triggers, procedures, indexes |
| Person 2 | Backend Developer | `backend-api` | FastAPI endpoints, booking logic, concurrency control, transactions |
| Person 3 | Distributed + NoSQL | `distributed-nosql` | MongoDB integration, Docker setup, 3-node MySQL config, replication |
| Person 4 | Frontend Developer | `frontend-ui` | React UI, booking flow, live dashboard, admin panel |

---

## Git Workflow

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/ev-charging-network.git
cd ev-charging-network
```

### 2. Create your feature branch
```bash
# Person 1
git checkout -b database-schema

# Person 2
git checkout -b backend-api

# Person 3
git checkout -b distributed-nosql

# Person 4
git checkout -b frontend-ui
```

### 3. Work on your part
Make changes, commit frequently with clear messages.

```bash
git add .
git commit -m "feat(database): add users and vehicles tables"
```

### 4. Push your branch
```bash
git push origin your-branch-name
```

### 5. Open a Pull Request
- Go to GitHub
- Click "New Pull Request"
- Select your branch → `main`
- Add a clear title and description
- Request review from one other team member

### 6. After approval, merge to main
Once reviewed and approved, merge your PR.

---

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

Examples:
feat(backend): add booking endpoint with 2PL
fix(database): correct foreign key constraint
docs(readme): update setup instructions
chore(docker): update compose file for MongoDB
```

**Types:**
- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation only
- `chore` — maintenance (dependencies, config)
- `refactor` — code restructuring
- `test` — adding tests

---

## Code Style

### Backend (Python)
- Follow PEP 8
- Use `black` for formatting
- Run `flake8` before committing

```bash
black app/
flake8 app/
```

### Frontend (React)
- Use functional components with hooks
- Follow React best practices
- Keep components small and reusable

### Database (SQL)
- Use uppercase for SQL keywords
- Add comments for complex queries
- Follow naming conventions:
  - Tables: plural, snake_case (e.g., `charger_units`)
  - Columns: snake_case (e.g., `user_id`)
  - Indexes: `idx_<table>_<column>`

---

## Testing Before Push

### Backend
```bash
cd backend
pytest
```

### Frontend
```bash
cd frontend
npm test
```

### Docker
```bash
docker-compose up --build
# Check that all services start without errors
```

---

## Pull Request Checklist

Before opening a PR, ensure:

- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] Docker containers build successfully
- [ ] No merge conflicts with `main`
- [ ] Clear commit messages
- [ ] PR description explains what changed and why

---

## Need Help?

- Open an issue for bugs or questions
- Tag the relevant person in comments
- Use the team group chat

---

Happy coding! 🚀
