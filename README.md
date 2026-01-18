# GitPR CLI 🚀

**GitPR** is an exclusive, "batteries-included" command-line tool designed for developers who want to manage GitHub Pull Requests without leaving the terminal.

Unlike standard tools, `gitpr` focuses on **interactive workflows**: it auto-detects your repository context, opens your favorite terminal editor (Vim/Nano) for descriptions, supports **GitHub Enterprise** natively, and integrates with **Slack** for team notifications.

---

## ✨ Features

* **Interactive Wizard:** No need to remember complex flags. The tool guides you through PR creation.
* **Editor First:** Writes PR bodies and comments using your system's default editor (Vim, Nano, VS Code).
* **Enterprise Ready:** First-class support for `github.your-company.com` domains.
* **Smart Context:** Auto-detects the repository (`org/repo`) from your current directory.
* **Issue Linking:** Seamlessly links new PRs to existing issues across any repo.
* **Team Notifications:** Optional Slack integration to broadcast new PRs to your team channel.

---

## 📦 Installation

Install `gitpr` globally using pip:

```bash
pip install gitpr-tool

```

*(Ensure you have Python 3.9+ installed)*

---

## ⚙️ Configuration

Before using the tool, you must authenticate. This one-time setup saves your credentials securely on your local machine.

```bash
gitpr login

```

**The Setup Wizard will ask:**

1. **Enterprise Mode:** Are you using public GitHub or a private Enterprise instance?
2. **Token:** Paste your Personal Access Token (PAT).
* *Scopes required:* `repo`, `read:org`, `user`.


3. **Slack Webhook (Optional):** Paste a webhook URL to enable team notifications.

---

## 🚀 Usage Guide

### 1. Creating a Pull Request

The core command. You can run it with flags or interactively.

**Basic Usage (Auto-detects repo):**

```bash
cd my-project
gitpr create --from feature-login --to main

```

**Advanced Usage (Explicit repo & Draft mode):**

```bash
gitpr create my-org/backend-api --from feature-login --to main --draft

```

**The Interactive Workflow:**

1. **Title:** You are prompted to enter a title.
2. **Description:** The tool checks for a `.github/pull_request_template.md`.
* It opens **Vim/Nano** pre-filled with the template.
* You write your description using full Markdown (checklists, headers, etc.).
* Save and quit to submit.


3. **Issue Linking:** * *System asks:* `Link this PR to an Issue? [y/N]`
* *You paste:* `https://github.com/my-org/my-repo/issues/50`
* *Result:* The tool adds a comment to Issue #50: *"PR Created: <link>"*



### 2. Adding Comments

Add detailed comments to existing PRs without leaving the terminal.

```bash
# Syntax: gitpr comment <PR_NUMBER>
gitpr comment 42

```

* **Smart Context:** It knows you are in `my-org/backend-api`, so it looks for PR #42 in that repo.
* **Safety Check:** It displays the PR Title ("Fix: Login Bug") to confirm you are commenting on the right ticket.
* **Editor:** Opens your editor so you can paste logs, screenshots (as links), or write long-form reviews.

---

## 🏢 Enterprise Guide

GitPR is built for the corporate environment.

**If your token expires:**
The tool performs a "Pre-Flight Check" before every command. If your token is expired or SSO has revoked access, it will fail gracefully:

```text
❌ Authentication Failed.
Your token has expired or is invalid.
Action: Please run 'gitpr login' to update your token.

```

**Issue Linking across Repos:**
You can link a PR in `code-repo` to an issue in `issue-tracker-repo`. The tool supports cross-repo linking even on private Enterprise domains.

---

## 🔔 Slack Integration

To enable Slack notifications:

1. Create an [Incoming Webhook](https://api.slack.com/messaging/webhooks) in your Slack workspace.
2. Run `gitpr login` and paste the URL when prompted.

**What it looks like:**
When you run `gitpr create`, your team sees:

> 🚀 **New PR Created** in `my-org/backend`
> **Title:** Fix Login Timeout
> **Link:** [https://github.com/](https://github.com/)...
> **Author:** @abc

---

## 🛠 Development

If you want to contribute or modify the source code:

1. Clone the repository.
2. Install dependencies:
```bash
pip install -e .

```


3. Run the tool locally:
```bash
gitpr --help

```



---

## 📝 License

This project is licensed under the MIT License.

---

*Built with ❤️ using [Typer](https://typer.tiangolo.com/) and [PyGithub](https://github.com/PyGithub/PyGithub).*