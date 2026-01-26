# src/gitpr/main.py
import typer
import json
import re
import requests
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from git import Repo, InvalidGitRepositoryError
from cryptography.fernet import Fernet
from gitpr.forges import GitHubForge, GitLabForge, Forge

# --- SETUP ---
app = typer.Typer(help="The Universal Git CLI Tool")
console = Console()
APP_NAME = "gitpr"
CONFIG_PATH = Path(typer.get_app_dir(APP_NAME)) / "config.json"
KEY_PATH = Path(typer.get_app_dir(APP_NAME)) / ".key"

# --- SECURITY UTILS ---
def load_or_create_key():
    if not KEY_PATH.exists():
        if not KEY_PATH.parent.exists(): KEY_PATH.parent.mkdir(parents=True)
        key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as f: f.write(key)
        try: KEY_PATH.chmod(0o600)
        except: pass
    with open(KEY_PATH, "rb") as f: return f.read()

def encrypt_token(token: str) -> str:
    f = Fernet(load_or_create_key())
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    f = Fernet(load_or_create_key())
    return f.decrypt(encrypted_token.encode()).decode()

def load_config():
    if not CONFIG_PATH.exists():
        console.print("[bold red]Not logged in.[/bold red]")
        raise typer.Exit(code=1)
    with open(CONFIG_PATH, "r") as f: return json.load(f)

# --- FACTORY ---
def get_forge(repo_context: str) -> Forge:
    config = load_config()
    repo = Repo(".")
    remote_url = repo.remotes.origin.url
    
    provider = "github"
    if "gitlab" in remote_url:
        provider = "gitlab"
    
    if provider not in config:
        console.print(f"[red]No config for {provider}. Run `gitpr login --provider {provider}`[/red]")
        raise typer.Exit(1)
        
    prov_conf = config[provider]
    try:
        token = decrypt_token(prov_conf["token"])
    except:
        console.print("[red]Token decrypt failed. Re-login.[/red]")
        raise typer.Exit(1)
        
    if provider == "github":
        return GitHubForge(token, prov_conf["base_url"], repo_context)
    else:
        return GitLabForge(token, prov_conf["base_url"], repo_context)

def get_current_repo_context():
    try:
        repo = Repo(".", search_parent_directories=True)
        remote_url = repo.remotes.origin.url
        match = re.search(r"[:/]([\w-]+)/([\w-]+)(?:\.git)?$", remote_url)
        if match: return f"{match.group(1)}/{match.group(2)}"
        return None
    except: return None

# --- COMMANDS ---

@app.command()
def login(
    provider: str = typer.Option("github", "--provider", "-p", help="github or gitlab")
):
    """Login to GitHub or GitLab (Supports Enterprise)."""
    console.rule(f"[bold blue]Setup {provider.upper()}[/bold blue]")
    
    # 1. Provider Setup
    base_url = "https://api.github.com" if provider == "github" else "https://gitlab.com"
    if typer.confirm("Is this an Enterprise instance?", default=False):
        domain = typer.prompt("Enter Domain (e.g. gitlab.company.com)")
        base_url = f"https://{domain}/api/v3" if provider == "github" else f"https://{domain}"

    token = typer.prompt(f"Paste {provider.title()} Token", hide_input=True)
    encrypted_token = encrypt_token(token)

    # Load existing config
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f: config = json.load(f)

    # Save Provider Config
    config[provider] = {"token": encrypted_token, "base_url": base_url}
    
    # 2. Slack Setup (Global)
    # Only ask if not already configured, or if user explicitly wants to update it
    configure_slack = True
    if "slack_webhook" in config:
        configure_slack = typer.confirm("Slack is already configured. Update it?", default=False)
    elif typer.confirm("Configure Slack notifications?", default=False):
        pass # User said yes
    else:
        configure_slack = False

    if configure_slack:
        webhook = typer.prompt("Paste Slack Webhook URL")
        config["slack_webhook"] = webhook
        console.print("[green]✔ Slack configuration updated.[/green]")
    
    # 3. Save to Disk
    if not CONFIG_PATH.parent.exists(): CONFIG_PATH.parent.mkdir(parents=True)
    with open(CONFIG_PATH, "w") as f: json.dump(config, f)
    try: CONFIG_PATH.chmod(0o600)
    except: pass
        
    console.print(f"[green]✔ {provider.title()} configuration saved.[/green]")

@app.command()
def create(
    from_branch: str = typer.Option(..., "--from", "-f"),
    to_branch: str = typer.Option(..., "--to", "-t"),
    draft: bool = typer.Option(False, "--draft")
):
    """Create a PR/MR."""
    ctx = get_current_repo_context()
    forge = get_forge(ctx)
    config = load_config()
    
    console.rule(f"[bold blue]Creating Request: {ctx}[/bold blue]")
    title = typer.prompt("Title")
    body = typer.edit(extension=".md")
    
    with console.status("[green]Creating...[/green]"):
        try:
            pr = forge.create_pr(title, body if body else "", from_branch, to_branch, draft)
            console.print(f"\n[bold green]✔ Created![/bold green] [link={pr.url}]{pr.url}[/link]")

            if "slack_webhook" in config:
                payload = {
                    "text": f"🚀 *New PR* in `{ctx}`\n*Title:* {title}\n*Author:* {forge.get_user()}\n*Link:* {pr.url}"
                }
                try:
                    requests.post(config["slack_webhook"], json=payload, timeout=5)
                    console.print("[dim]✔ Slack notification sent.[/dim]")
                except Exception as e:
                    console.print(f"[yellow]⚠ Failed to send Slack notification: {e}[/yellow]")
        except Exception as e:
            console.print(f"[red]Failed:[/red] {e}")

@app.command()
def diff(pr_number: int, show_all: bool = typer.Option(False, "--all", "-a")):
    """View Changes (Diffs) - Read Only."""
    ctx = get_current_repo_context()
    forge = get_forge(ctx)
    
    console.rule(f"[bold blue]Diff View: #{pr_number}[/bold blue]")
    with console.status("Fetching files..."):
        files = forge.get_files(pr_number)
        
    table = Table(title="Changed Files")
    table.add_column("File", style="cyan")
    table.add_column("Stats", justify="right")
    for f in files:
        table.add_row(f.filename, f"+{f.additions} -{f.deletions}")
    console.print(table)
    
    if not show_all and not typer.confirm("View diffs?"): raise typer.Exit()
    
    for f in files:
        console.rule(f"[yellow]{f.filename}[/yellow]")
        if f.patch:
            console.print(Syntax(f.patch, "diff", theme="monokai", line_numbers=False))
        else:
            console.print("[dim]No diff available[/dim]")
        if not show_all: typer.prompt("Next...", show_default=False)

@app.command()
def review(pr_number: int):
    """Approve or Request Changes."""
    ctx = get_current_repo_context()
    forge = get_forge(ctx)
    pr = forge.get_pr(pr_number)
    
    console.print(f"[bold]{pr.title}[/bold] by {pr.author}")
    action = typer.prompt("Action? (approve/request/comment/skip)").lower()
    
    event_map = {"approve": "APPROVE", "request": "REQUEST_CHANGES", "comment": "COMMENT"}
    if action not in event_map: raise typer.Exit()
    
    msg = typer.prompt("Message")
    forge.submit_review(pr_number, event_map[action], msg)
    console.print("[green]✔ Review Submitted.[/green]")

@app.command()
def edit(pr_number: int):
    """Edit Title/Description."""
    ctx = get_current_repo_context()
    forge = get_forge(ctx)
    pr = forge.get_pr(pr_number)
    
    console.rule(f"[bold blue]Editing #{pr_number}[/bold blue]")
    new_title = typer.prompt("Title", default=pr.title)
    new_body = typer.edit(pr.body, extension=".md")
    
    with console.status("Updating..."):
        forge.edit_pr(pr_number, title=new_title, body=new_body if new_body else pr.body)
    console.print("[green]✔ Updated![/green]")

@app.command()
def comment(pr_number: int):
    """Add a comment."""
    ctx = get_current_repo_context()
    forge = get_forge(ctx)
    
    body = typer.edit(extension=".md")
    if not body: raise typer.Exit()
    
    forge.comment(pr_number, body)
    console.print("[green]✔ Comment added.[/green]")

@app.command()
def cleanup(branch: str):
    """Delete a merged branch locally and remotely."""
    ctx = get_current_repo_context()
    forge = get_forge(ctx)
    
    # 1. Check Remote Status
    with console.status("Checking merge status..."):
        merged_branches = forge.find_merged_branches()
        is_merged = branch in merged_branches
    
    if is_merged:
        console.print(f"[green]✔ Remote branch '{branch}' is merged.[/green]")
    else:
        console.print(f"[red]⚠ Remote branch '{branch}' is NOT merged.[/red]")
        
    # 2. Remote Deletion
    if typer.confirm(f"Delete remote branch '{branch}'?"):
        try:
            forge.delete_remote_branch(branch)
            console.print("✔ Remote deleted.")
        except Exception as e:
             console.print(f"[red]Error:[/red] {e}")

    # 3. Local Deletion
    try:
        local_repo = Repo(".")
        if branch in local_repo.heads:
            if typer.confirm(f"Delete local branch '{branch}'?"):
                flag = "-D" if not is_merged else "-d"
                local_repo.git.branch(flag, branch)
                console.print("✔ Local deleted.")
    except Exception as e:
        console.print(f"[dim]Local delete skipped: {e}[/dim]")

def main():
    app()

if __name__ == "__main__":
    main()