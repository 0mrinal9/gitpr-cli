# `gitpr` 🚀

**The Universal, "Batteries-Included" CLI for GitHub & GitLab.**

`gitpr` is a modern, enterprise-ready command-line tool that unifies your workflow across **GitHub** and **GitLab**. It auto-detects your environment and provides a powerful, terminal-based interface to manage Pull Requests (PRs) and Merge Requests (MRs).

Whether you are on public GitHub, a private GitHub Enterprise instance, or a self-hosted GitLab server, `gitpr` speaks the language of your forge so you don't have to context-switch.

---

## ✨ Features & Comparison

Why use `gitpr` instead of `gh` or `glab`?

| Feature | `gitpr` 🚀 | Standard CLI (`gh`/`glab`) |
| --- | --- | --- |
| **Universal Support** | Works with **both** GitHub & GitLab seamlessly. | Locked to one vendor. |
| **Slack Integration** | Auto-notifies your team channel on new PRs. | Requires external actions/bots. |
| **Enterprise Ready** | Native support for custom domains & proxies. | Often requires complex config. |
| **Smart Janitor** | Safely cleans local branches *only* if merged. | Manual deletion required. |
| **Interactive Review** | Review diffs, approve, & request changes in one flow. | Mostly read-only or web-redirect. |
| **Permalinks** | Generates commit-locked links for files/lines. | Not supported. |
| **Security** | AES-256 Encrypted credentials on disk. | Plain text storage (often). |

---

## 📦 Installation

Requires **Python 3.10+**.

### From PyPI (Coming Soon)

```bash
pip install gitpr

```

### From Source (Recommended)

```bash
git clone https://github.com/0mrinal9/gitpr-cli.git
cd gitpr-cli
pip install -e .

```

---

## ⚙️ Configuration

`gitpr` supports a **Multi-Profile Login** system. You can be logged into GitHub (Public), GitHub Enterprise, and GitLab simultaneously.

### 1. GitHub Setup

```bash
gitpr login --provider github

```

* **Public:** Press Enter when asked for the domain.
* **Enterprise:** Enter your custom domain (e.g., `github.acme.com`).
* **Token:** Paste your Personal Access Token (PAT). It is **encrypted immediately**.

### 2. GitLab Setup

```bash
gitpr login --provider gitlab

```

* **Public:** Defaults to `gitlab.com`.
* **Enterprise:** Enter your instance domain (e.g., `gitlab.internal.net`).

### 3. Slack Integration 💬

During login, the tool will ask:

> `Configure Slack notifications? [y/N]`

If you say **Yes**, you will be prompted for a **Webhook URL**.

1. Go to [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks).
2. Create a webhook for your team's channel (e.g., `#dev-team`).
3. Paste the URL (starts with `https://hooks.slack.com/...`).

**Result:** Every time you run `gitpr create`, a notification with the PR link and author will be posted to that channel automatically.

---

## 💻 Command Reference

`gitpr` relies on **Smart Detection**: it looks at your current folder's `.git` config to figure out the `org/repo`.

**Override:** You can override this by explicitly passing `[ORG/REPO]` as the last argument to most commands. This is useful if you want to manage a repository without `cd`-ing into it.

### 1. `create`

Opens a new Pull Request (GitHub) or Merge Request (GitLab).

```bash
# Syntax
gitpr create [OPTIONS] [ORG/REPO]

# Auto-detect repo (run inside folder)
gitpr create --from feature-login --to main

# Explicit repo (run from anywhere)
gitpr create --from feature-login --to main my-org/backend-api

```

**Options:**

* `--draft`: Creates the PR/MR in "Draft" mode.
* *Interactive Mode:* If you omit flags, it will prompt you for the title and open your default editor.
* *Slack:* Automatically sends a notification if configured.

### 2. `review`

The core interactive review tool. Fetch details, view status, and submit reviews.

```bash
# Syntax
gitpr review <PR_NUMBER> [ORG/REPO]

# Example
gitpr review 42
gitpr review 42 my-org/backend-api

```

**Workflow:**

1. **Summary:** Shows file stats (files changed, additions, deletions).
2. **Action Prompt:** Asks you to select an action:
* `approve`: Submit an "Approve" review.
* `request`: Submit "Request Changes" (blocks merging).
* `comment`: Submit a general comment.
* `skip`: Exit without reviewing.



### 3. `diff`

Read-only mode for inspecting code changes.

```bash
# Syntax
gitpr diff <PR_NUMBER> [ORG/REPO] [OPTIONS]

# Example
gitpr diff 42 --all

```

**Options:**

* `--all` / `-a`: Shows all file diffs immediately without asking "Show next file?" (Great for piping to pagers).

### 4. `cleanup` (The Janitor)

Safely deletes a local branch **only if** it has been merged on the remote.

```bash
# Syntax
gitpr cleanup <BRANCH_NAME> [ORG/REPO]

# Example
gitpr cleanup feature-login

```

**Logic:**

1. Checks Remote: "Is this branch merged?"
2. **If Merged:** Prompts to delete Remote branch -> Then prompts to delete Local branch.
3. **If Unmerged:** Warns you and aborts (unless forced using `-f` or `--force`).

### 5. `edit`

Modify the metadata of an existing PR/MR.

```bash
# Syntax
gitpr edit <PR_NUMBER> [ORG/REPO]

```

* Fetches current Title and Description.
* Opens your editor to let you modify them.
* Pushes updates immediately.

### 6. `comment`

Quickly add a simple comment to a PR without a full review.

```bash
# Syntax
gitpr comment <PR_NUMBER> [ORG/REPO]

```

* Opens editor for comment body -> Posts immediately.

### 7. `link`

Generates a permanent, commit-locked URL (permalink) to a specific file. This is essential for referencing code or assets in PR descriptions so the links never break.

*> Note: This command **requires** you to be inside the git folder.*

```bash
# Syntax
gitpr link <FILEPATH> [OPTIONS]

```

**Examples:**

* **Link to Code (Reviewing Logic):**
```bash
gitpr link src/auth.py --lines 50-60

```


> Output: `https://github.com/org/repo/blob/a1b2c3d/src/auth.py#L50-L60`


* **Link to an Image (Embedding Screenshots):**
```bash
gitpr link assets/login-error.png

```


> Output: `https://github.com/org/repo/blob/a1b2c3d/assets/login-error.png`
> *Tip: Paste this url into your PR description like `![Error](URL)` to display it.*


* **Link to a Video (Demo Clips):**
```bash
gitpr link demos/new-feature.mp4

```


> Output: `https://github.com/org/repo/blob/a1b2c3d/demos/new-feature.mp4`



**Options:**

* `--lines` / `-l`: Highlight specific lines (e.g., `10` or `10-20`). Only valid for text files.

---

## 🏢 Enterprise Support

`gitpr` is designed for complex corporate network environments.

### 1. Proxy Support

If you are behind a corporate firewall, `gitpr` respects standard environment variables.

```bash
# Linux/Mac
export HTTPS_PROXY="http://proxy.corporation.com:8080"
export HTTP_PROXY="http://proxy.corporation.com:8080"

# Windows (PowerShell)
$env:HTTPS_PROXY = "http://proxy.corporation.com:8080"

```

### 2. Custom Domains

Supports **GitHub Enterprise Server (GHES)** and self-hosted **GitLab**. Just provide the full domain during `gitpr login`.

### 3. SSL/TLS Certificates

For on-premise instances using internal Certificate Authorities (Self-Signed Certs):

* Ensure your Python environment trusts the CA.
* Or set `REQUESTS_CA_BUNDLE=/path/to/corporate-ca.pem`.

---

## 🔐 Security Considerations

We treat security as a first-class citizen.

1. **Encryption at Rest:**
* API Tokens are encrypted using **AES-256 (Fernet)**.
* The encryption key is unique to your machine (`~/.gitpr/.key`).
* Config file (`config.json`) contains only encrypted blobs, never plain text.


2. **Input Sanitization:**
* All internal Git commands use the `--` separator to prevent Argument Injection attacks via malicious branch names.
* The `link` command blocks Path Traversal (`..`) attempts.


3. **Supply Chain Security:**
* We use **pip-audit** to scan dependencies for known CVEs.
* CI pipelines are configured to fail if a vulnerability is detected.


4. **File Permissions:**
* On Unix/Mac, the key file is restricted to `600` (Read/Write by owner only).
* On Windows, the key file is set to Read-Only to prevent accidental modification.



---

## 🛠️ Development

Want to contribute?

### 1. Setup

```bash
# Clone
git clone https://github.com/your-org/gitpr.git

# Install with Dev dependencies
pip install -e ".[dev]"

```

### 2. Run Security Audit

Before submitting a PR, ensure dependencies are secure:

```bash
pip-audit

```

---

## 🏗️ Tech Stack

* **[Typer](https://typer.tiangolo.com/):** CLI framework.
* **[Rich](https://github.com/Textualize/rich):** Terminal formatting (tables, colors, markdown).
* **[PyGithub](https://github.com/PyGithub/PyGithub):** GitHub API interaction.
* **[python-gitlab](https://python-gitlab.readthedocs.io/):** GitLab API interaction.
* **[GitPython](https://gitpython.readthedocs.io/):** Local git operations.
* **[Cryptography](https://cryptography.io/):** AES encryption.

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.

Copyright (c) 2026.