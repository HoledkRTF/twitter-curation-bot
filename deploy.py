import os
import requests
import json
import subprocess
import time

GH_TOKEN = "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"
RENDER_TOKEN = "rnd_ZhomIk8rTIpYUm92THQ37g5yQTkU"

BOT_DIR = r"C:\Users\clint\.gemini\antigravity\scratch\goon-tools\twitter-curation-bot"
REPO_NAME = "twitter-curation-bot"

# 1. Create GitHub Repo
print("Creating GitHub Repo...")
gh_headers = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}
res = requests.post("https://api.github.com/user/repos", headers=gh_headers, json={
    "name": REPO_NAME,
    "private": True
})
if res.status_code in [201, 200, 422]: # 422 means already exists, which is fine
    print("Repo created or already exists.")
else:
    print(f"Failed to create repo: {res.text}")
    exit(1)

# Get GitHub username
user_res = requests.get("https://api.github.com/user", headers=gh_headers)
gh_username = user_res.json()["login"]
repo_url = f"https://github.com/{gh_username}/{REPO_NAME}.git"

# 2. Push Code
print("Pushing code to GitHub...")
os.chdir(BOT_DIR)
# Remove old git if exists
subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", ".git"])
subprocess.run(["git", "init"])
subprocess.run(["git", "add", "bot.py", "requirements.txt", "config.json"])
subprocess.run(["git", "config", "user.email", "bot@example.com"])
subprocess.run(["git", "config", "user.name", "Bot"])
subprocess.run(["git", "commit", "-m", "Initial commit"])
subprocess.run(["git", "branch", "-M", "main"])
# Inject token into origin URL so push works silently without prompt
auth_repo_url = f"https://{gh_username}:{GH_TOKEN}@github.com/{gh_username}/{REPO_NAME}.git"
subprocess.run(["git", "remote", "add", "origin", auth_repo_url])
subprocess.run(["git", "push", "-u", "origin", "main", "--force"])

# 3. Create Render Web Service
print("Deploying to Render...")
render_headers = {
    "Authorization": f"Bearer {RENDER_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# We need the user's ownerId for Render
owner_res = requests.get("https://api.render.com/v1/owners", headers=render_headers)
owner_id = owner_res.json()[0]["owner"]["id"]

# Read config to get vars
with open("config.json", "r") as f:
    cfg = json.load(f)

payload = {
    "type": "web_service",
    "name": REPO_NAME,
    "ownerId": owner_id,
    "repo": repo_url,
    "autoDeploy": "yes",
    "branch": "main",
    "serviceDetails": {
        "region": "singapore",
        "env": "python",
        "envSpecificDetails": {
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python bot.py"
        },
        "plan": "free"
    },
    "envVars": [
        {"key": "TELEGRAM_BOT_TOKEN", "value": cfg['telegram_bot_token']},
        {"key": "TELEGRAM_CHANNEL_ID", "value": cfg['telegram_channel_id']},
        {"key": "TWITTER_LIST_URL", "value": cfg['twitter_list_url']},
        {"key": "APIFY_API_TOKEN", "value": cfg['apify_api_token']}
    ]
}

res = requests.post("https://api.render.com/v1/services", headers=render_headers, json=payload)
if res.status_code == 201:
    svc = res.json()
    print("Successfully created Render service!")
    print(f"Service URL: {svc['service']['serviceDetails']['url']}")
    print(f"Dashboard URL: {svc['service']['dashboardUrl']}")
else:
    print(f"Failed to create Render service: {res.text}")
