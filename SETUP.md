# Setup Guide — Push to GitHub

Your local repo is ready. Here's how to push it to GitHub:

---

## Step 1: Create the GitHub Repo

1. Go to https://github.com/new
2. Repository name: **`ev-charging-network`**
3. Description: *Multi-city EV charging station booking platform — BACSE202 DB Systems Project*
4. **Keep it Private** (for now, make it public later if needed)
5. **Do NOT** initialize with README, .gitignore, or license (we already have them)
6. Click **Create repository**

---

## Step 2: Push Your Local Code

GitHub will show you commands. Use these (replace `YOUR_USERNAME` with your actual GitHub username):

```bash
cd ~/ev-charging-network

# Add the remote
git remote add origin https://github.com/YOUR_USERNAME/ev-charging-network.git

# Push to GitHub
git push -u origin main
```

**If you're using SSH instead of HTTPS:**
```bash
git remote add origin git@github.com:YOUR_USERNAME/ev-charging-network.git
git push -u origin main
```

---

## Step 3: Verify

Go to your repo on GitHub: `https://github.com/YOUR_USERNAME/ev-charging-network`

You should see:
- ✅ All folders and files
- ✅ README with full project description
- ✅ 22 files in the initial commit

---

## Step 4: Add Your Team as Collaborators

1. Go to your repo on GitHub
2. Click **Settings** (top right)
3. Click **Collaborators** (left sidebar)
4. Click **Add people**
5. Enter each team member's GitHub username or email
6. They'll get an invite to accept

---

## Step 5: Tell Your Team to Clone

Each team member runs:

```bash
git clone https://github.com/YOUR_USERNAME/ev-charging-network.git
cd ev-charging-network
```

Then they check out their branch:

```bash
# Person 1 (Database)
git checkout -b database-schema

# Person 2 (Backend)
git checkout -b backend-api

# Person 3 (Distributed + NoSQL)
git checkout -b distributed-nosql

# Person 4 (Frontend)
git checkout -b frontend-ui
```

---

## Step 6: Test the Setup

Everyone should test that Docker works:

```bash
docker-compose up --build
```

This will:
- Start 3 MySQL nodes (Bangalore, Chennai, Delhi)
- Start MongoDB
- Start Backend API
- Start Frontend

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

If all 5 containers start without errors, you're good to go.

---

## Next Steps

- Each person works on their own branch
- Commit + push regularly
- Open PRs when a feature is done
- Get one other person to review before merging

Refer to [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

---

**Questions?** Open an issue or ask in the team chat.
