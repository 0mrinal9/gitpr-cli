import typer
import json
import requests
import re
import os
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.markdown import Markdown
from github import Github, GithubException
from git import Repo, InvalidGitRepositoryError
from cryptography.fernet import Fernet

# --- CONFIGURATION & SETUP ---
app = typer.Typer(help="The Exclusive GitHub CLI Tool")
console = Console()
APP_NAME = "gitpr"
CONFIG_PATH = Path(typer.get_app_dir(APP_NAME)) / "config.json"
KEY_PATH = Path(typer.get_app_dir(APP_NAME)) / ".key"

# --- SECURITY & ENCRYPTION HELPERS ---

def load_or_create_key():
    """Loads encryption key or generates a new one securely."""
    if not KEY_PATH.exists():
        if not KEY_PATH.parent.exists():
            KEY_PATH.parent.mkdir(parents=True)
        key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as f:
            f.write(key)
        # Set permission to read/write only by owner (Unix/Linux/Mac)
        try:
            KEY_PATH.chmod(0o600)
        except:
            pass # Windows permissions handle this differently, safe to ignore
    
    with open(KEY_PATH, "rb") as f:
        return f.read()

def encrypt_token(token: str) -> str:
    key = load_or_create_key()
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    key = load_or_create_key()
    f = Fernet(key)
    return f.decrypt(encrypted_token.encode()).decode()

# --- GENERAL HELPERS ---

def load_config():
    """Loads config securely."""
    if not CONFIG_PATH.exists():
        console.print("[bold red]Not logged in.[/bold red] Please run `gitpr login` first.")
        raise typer.Exit(code=1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def get_github_client(config):
    """Initializes GitHub client, decrypts token, and verifies auth."""
    try:
        token = decrypt_token(config["token"])
    except Exception:
        console.print("[bold red]❌ Security Error:[/bold red] Could not decrypt token.")
        console.print("Please run [bold]gitpr login[/bold] again.")
        raise typer.Exit(1)

    g = Github(base_url=config["base_url"], login_or_token=token)
    
    try:
        # Lightweight call to verify token validity
        _ = g.get_user().login
    except GithubException as e:
        if e.status == 401:
            console.print("[bold red]❌ Authentication Failed.[/bold red]")
            console.print("Your token has expired or is invalid.")
            raise typer.Exit(code=1)
        else:
            raise e
    return g

def get_current_repo_context():
    """Detects org/repo from .git folder."""
    try:
        repo = Repo(".", search_parent_directories=True)
        remote_url = repo.remotes.origin.url
        # Parse SSH or HTTPS
        match = re.search(r"[:/]([\w-]+)/([\w-]+)(?:\.git)?$", remote_url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return None
    except (InvalidGitRepositoryError, AttributeError):
        return None

# --- COMMANDS ---

@app.command()
def login():
    """Setup GitHub Token (Encrypted) and Integrations."""
    console.print(Panel("[bold blue]GitPR Setup Wizard[/bold blue]", expand=False))
    
    is_enterprise = typer.confirm("Are you using GitHub Enterprise?", default=False)
    base_url = "https://api.github.com"
    if is_enterprise:
        domain = typer.prompt("Enter Enterprise Domain (e.g. github.acme.com)")
        base_url = f"https://{domain}/api/v3"

    console.print(f"\n[dim]Create token: {base_url.replace('/api/v3', '')}/settings/tokens[/dim]")
    token = typer.prompt("Paste GitHub Token", hide_input=True)

    # ENCRYPT TOKEN
    encrypted_token = encrypt_token(token)

    setup_slack = typer.confirm("Configure Slack notifications?", default=False)
    slack_webhook = None
    if setup_slack:
        slack_webhook = typer.prompt("Paste Slack Webhook URL")

    if not CONFIG_PATH.parent.exists():
        CONFIG_PATH.parent.mkdir(parents=True)
        
    config_data = {
        "token": encrypted_token,
        "base_url": base_url,
        "slack_webhook": slack_webhook
    }
    
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f)
    
    try:
        CONFIG_PATH.chmod(0o600)
    except:
        pass
        
    console.print(f"[green]✔ Secure configuration saved.[/green]")

@app.command()
def create(
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo"),
    from_branch: str = typer.Option(..., "--from", "-f", help="Source Branch"),
    to_branch: str = typer.Option(..., "--to", "-t", help="Target Branch"),
    draft: bool = typer.Option(False, "--draft", help="Create as Draft")
):
    """Create a new Pull Request."""
    config = load_config()
    
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ Could not detect repository.[/red]")
            raise typer.Exit(1)
    
    with console.status("[dim]Connecting...[/dim]"):
        g = get_github_client(config)
        try:
            repo = g.get_repo(repo_arg)
        except GithubException:
            console.print(f"[red]❌ Access denied to {repo_arg}.[/red]")
            raise typer.Exit(1)

    console.rule(f"[bold blue]Creating PR: {repo_arg}[/bold blue]")
    title = typer.prompt("Enter PR Title")

    # Fetch Template
    template_content = ""
    for path in [".github/pull_request_template.md", "pull_request_template.md"]:
        try:
            template_content = repo.get_contents(path, ref=to_branch).decoded_content.decode()
            break
        except: pass
    
    body = typer.edit(template_content if template_content else "", extension=".md")
    if not body and not typer.confirm("Body is empty. Continue?"):
        raise typer.Exit()

    with console.status("[bold green]Creating PR...[/bold green]"):
        try:
            pr = repo.create_pull(
                title=title, body=body if body else "", 
                head=from_branch, base=to_branch, draft=draft
            )
        except GithubException as e:
            console.print(f"[red]Failed:[/red] {e.data.get('message', e)}")
            raise typer.Exit(1)

    console.print(f"\n[bold green]✔ PR Created![/bold green] [link={pr.html_url}]{pr.html_url}[/link]")

    # Issue Linking
    if typer.confirm("Link this PR to an Issue?"):
        issue_url = typer.prompt("Enter Issue URL")
        match = re.search(r"/([\w-]+)/([\w-]+)/issues/(\d+)", issue_url)
        if match:
            tgt_org, tgt_repo_name, tgt_issue_num = match.groups()
            try:
                tgt_repo = g.get_repo(f"{tgt_org}/{tgt_repo_name}")
                tgt_issue = tgt_repo.get_issue(int(tgt_issue_num))
                tgt_issue.create_comment(f"PR Created: {pr.html_url}")
                console.print(f"[green]✔ Linked to #{tgt_issue_num}[/green]")
            except Exception as e: console.print(f"[red]Failed to link: {e}[/red]")

    # Slack
    if config.get("slack_webhook"):
        payload = {"text": f"🚀 *New PR* in `{repo_arg}`\n*Title:* {title}\n*Link:* {pr.html_url}"}
        try:
            requests.post(config["slack_webhook"], json=payload, timeout=10)
        except: pass

@app.command()
def edit(
    pr_number: int,
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo")
):
    """Edit Title/Body of an existing PR."""
    config = load_config()
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ No repo context.[/red]")
            raise typer.Exit(1)

    g = get_github_client(config)
    try:
        repo = g.get_repo(repo_arg)
        pr = repo.get_pull(pr_number)
    except GithubException:
        console.print(f"[red]PR #{pr_number} not found.[/red]")
        raise typer.Exit(1)

    console.rule(f"[bold blue]Editing PR #{pr_number}[/bold blue]")
    new_title = typer.prompt("Title", default=pr.title)
    
    console.print("[dim]Opening editor for description...[/dim]")
    new_body = typer.edit(pr.body, extension=".md")

    if new_body is None:
        new_body = pr.body

    with console.status("[green]Updating PR...[/green]"):
        pr.edit(title=new_title, body=new_body)
    
    console.print(f"[bold green]✔ PR Updated![/bold green]")

@app.command()
def comment(
    pr_number: int,
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo")
):
    """Add a comment to a PR."""
    config = load_config()
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ No repo context.[/red]")
            raise typer.Exit(1)

    g = get_github_client(config)
    try:
        repo = g.get_repo(repo_arg)
        pr = repo.get_pull(pr_number)
    except GithubException:
        console.print(f"[red]PR #{pr_number} not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Commenting on PR #{pr_number}[/blue]")
    body = typer.edit(extension=".md")
    if not body or not body.strip():
        console.print("[yellow]Empty comment. Aborted.[/yellow]")
        raise typer.Exit()

    pr.create_issue_comment(body)
    console.print(f"[green]✔ Comment added![/green]")

@app.command()
def diff(
    pr_number: int,
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all diffs immediately without prompting")
):
    """
    View changes in a PR (Read-Only). Shows file summary and code diffs.
    """
    config = load_config()
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ No repo context.[/red]")
            raise typer.Exit(1)

    g = get_github_client(config)
    try:
        repo = g.get_repo(repo_arg)
        pr = repo.get_pull(pr_number)
    except GithubException:
        console.print(f"[red]PR #{pr_number} not found.[/red]")
        raise typer.Exit(1)

    # Header
    console.rule(f"[bold blue]Viewing Changes: PR #{pr_number}[/bold blue]")
    console.print(f"Title: [bold]{pr.title}[/bold]")
    console.print(f"Link:  {pr.html_url}\n")

    # File Summary Table
    with console.status("[dim]Fetching diffs...[/dim]"):
        files = list(pr.get_files())

    table = Table(title="Changed Files", show_header=True, header_style="bold magenta")
    table.add_column("File Name", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("+", style="green", justify="right")
    table.add_column("-", style="red", justify="right")

    for file in files:
        table.add_row(file.filename, file.status, f"+{file.additions}", f"-{file.deletions}")
    
    console.print(table)
    console.print(f"\n[dim]Total files: {len(files)}[/dim]\n")

    # Diff Viewer Logic
    if not show_all:
        if not typer.confirm("Inspect code diffs now?"):
            raise typer.Exit()

    for file in files:
        console.rule(f"[bold yellow]File: {file.filename}[/bold yellow]")
        if file.patch:
            # Syntax Highlighted Diff
            syntax = Syntax(file.patch, "diff", theme="monokai", line_numbers=False)
            console.print(syntax)
        else:
            console.print("[dim italic]No diff available (Binary or Large File).[/dim italic]")
        
        # Pause unless --all flag is used
        if not show_all:
            typer.prompt("\nPress Enter for next file...", default="", show_default=False)

@app.command()
def review(
    pr_number: int,
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo")
):
    """
    Submit a formal review (Approve, Request Changes, or Comment).
    """
    config = load_config()
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ No repo context.[/red]")
            raise typer.Exit(1)

    g = get_github_client(config)
    try:
        repo = g.get_repo(repo_arg)
        pr = repo.get_pull(pr_number)
    except GithubException:
        console.print(f"[red]PR #{pr_number} not found.[/red]")
        raise typer.Exit(1)

    # Context Header
    console.rule(f"[bold blue]Submitting Review for PR #{pr_number}[/bold blue]")
    console.print(f"Title: [bold]{pr.title}[/bold]")
    console.print(f"User:  {pr.user.login}")
    console.print(f"State: {pr.state}")
    
    # Action Prompt
    action = typer.prompt(
        "Decision? (approve/request/comment)", 
    ).lower()

    try:
        if action == "approve":
            msg = typer.prompt("Approval Message", default="LGTM!")
            pr.create_review(event="APPROVE", body=msg)
            console.print("[bold green]✔ PR Approved successfully![/bold green]")

        elif action == "request":
            msg = typer.prompt("Reason for changes")
            if msg.strip():
                pr.create_review(event="REQUEST_CHANGES", body=msg)
                console.print("[bold red]✔ Changes Requested.[/bold red]")
            else:
                console.print("[yellow]Aborted: You must provide a reason to request changes.[/yellow]")

        elif action == "comment":
            msg = typer.prompt("Comment body")
            if msg.strip():
                pr.create_review(event="COMMENT", body=msg)
                console.print("[bold blue]✔ Review comment posted.[/bold blue]")
            else:
                console.print("[yellow]Aborted: Empty comment.[/yellow]")

        else:
            console.print("[yellow]Unknown action. Exiting.[/yellow]")
            
    except GithubException as e:
        console.print(f"[bold red]❌ GitHub Error:[/bold red] {e.data.get('message', e)}")
        console.print("[dim]You might not have permission to perform this action.[/dim]")

@app.command()
def cleanup(
    branch_name: str = typer.Argument(..., help="The branch to delete"),
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo. Auto-detected if missing.")
):
    """
    Delete a specific branch from GitHub (Remote) and locally.
    Checks merge status before deleting.
    """
    config = load_config()
    
    # 1. Context Detection
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ No repo context.[/red]")
            raise typer.Exit(1)

    g = get_github_client(config)
    try:
        repo = g.get_repo(repo_arg)
        git_branch = repo.get_branch(branch_name)
    except GithubException:
        console.print(f"[bold red]❌ Branch '{branch_name}' not found on remote {repo_arg}.[/bold red]")
        raise typer.Exit(1)

    # 2. Safety Check (Is it merged?)
    # We check if there are any associated Pull Requests that are merged
    pulls = repo.get_pulls(state='closed', head=f"{repo.owner.login}:{branch_name}")
    is_merged = False
    for pr in pulls:
        if pr.merged:
            is_merged = True
            break
    
    # 3. Status Report
    console.rule(f"[bold blue]Cleanup: {branch_name}[/bold blue]")
    if is_merged:
        console.print(f"Status: [bold green]✔ Merged[/bold green] (Safe to delete)")
    else:
        console.print(f"Status: [bold red]⚠ Unmerged[/bold red] (Data loss risk)")
        console.print("[yellow]Warning: This branch has not been merged into the default branch.[/yellow]")

    # 4. Confirm Remote Deletion
    if typer.confirm(f"Delete remote branch '{branch_name}' on GitHub?"):
        try:
            # PyGithub doesn't have a direct delete_branch, we use references
            ref = repo.get_git_ref(f"heads/{branch_name}")
            ref.delete()
            console.print(f"[green]✔ Remote branch '{branch_name}' deleted.[/green]")
        except GithubException as e:
            console.print(f"[red]Failed to delete remote:[/red] {e.data.get('message', e)}")

    # 5. Local Deletion
    # Check if local branch exists
    try:
        local_repo = Repo(".")
        if branch_name in local_repo.heads:
            if typer.confirm(f"Delete local branch '{branch_name}'?"):
                try:
                    # Force delete (-D) if remote is gone, otherwise standard (-d)
                    flag = "-D" if not is_merged else "-d"
                    local_repo.git.branch(flag, branch_name)
                    console.print(f"[green]✔ Local branch deleted.[/green]")
                except Exception as e:
                    console.print(f"[red]Failed locally:[/red] {e}")
        else:
            console.print("[dim]Branch does not exist locally. Skipping.[/dim]")
    except InvalidGitRepositoryError:
        pass # Not in a git folder, skip local cleanup

def main():
    app()

if __name__ == "__main__":
    main()