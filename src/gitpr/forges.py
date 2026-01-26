# src/gitpr/forge.py
from abc import ABC, abstractmethod
from typing import List, Optional
from github import Github, GithubException
import gitlab

# Data Models
class FileDiff:
    def __init__(self, filename, status, additions, deletions, patch):
        self.filename = filename
        self.status = status
        self.additions = additions
        self.deletions = deletions
        self.patch = patch

class StandardPR:
    """A generic PR object that looks the same whether from GitHub or GitLab"""
    def __init__(self, raw_obj, source="github"):
        self.raw = raw_obj
        self.source = source
        if source == "github":
            self.number = raw_obj.number
            self.title = raw_obj.title
            self.body = raw_obj.body
            self.url = raw_obj.html_url
            self.state = raw_obj.state
            self.author = raw_obj.user.login
            self.merged = raw_obj.merged
            self.head_ref = raw_obj.head.ref
        else: # gitlab
            self.number = raw_obj.iid
            self.title = raw_obj.title
            self.body = raw_obj.description
            self.url = raw_obj.web_url
            self.state = raw_obj.state
            self.author = raw_obj.author['username']
            self.merged = raw_obj.state == 'merged'
            self.head_ref = raw_obj.source_branch

# Abstract Interface
class Forge(ABC):
    @abstractmethod
    def get_user(self) -> str: pass
    @abstractmethod
    def create_pr(self, title: str, body: str, source: str, target: str, draft: bool) -> StandardPR: pass
    @abstractmethod
    def get_pr(self, number: int) -> StandardPR: pass
    @abstractmethod
    def get_files(self, number: int) -> List[FileDiff]: pass
    @abstractmethod
    def edit_pr(self, number: int, title: str = None, body: str = None): pass
    @abstractmethod
    def comment(self, number: int, body: str): pass
    @abstractmethod
    def submit_review(self, number: int, event: str, body: str): pass
    @abstractmethod
    def find_merged_branches(self) -> List[str]: pass
    @abstractmethod
    def delete_remote_branch(self, branch_name: str): pass

# GitHub Implementation
class GitHubForge(Forge):
    def __init__(self, token, base_url, repo_slug):
        self.g = Github(base_url=base_url, login_or_token=token)
        try:
            self.repo = self.g.get_repo(repo_slug)
        except:
            raise ValueError(f"Repo {repo_slug} not found on GitHub")

    def get_user(self):
        return self.g.get_user().login

    def create_pr(self, title, body, source, target, draft):
        pr = self.repo.create_pull(title=title, body=body, head=source, base=target, draft=draft)
        return StandardPR(pr, "github")

    def get_pr(self, number):
        return StandardPR(self.repo.get_pull(number), "github")

    def get_files(self, number):
        files = []
        for f in self.repo.get_pull(number).get_files():
            files.append(FileDiff(f.filename, f.status, f.additions, f.deletions, f.patch))
        return files

    def edit_pr(self, number, title=None, body=None):
        kwargs = {}
        if title: kwargs['title'] = title
        if body: kwargs['body'] = body
        self.repo.get_pull(number).edit(**kwargs)

    def comment(self, number, body):
        self.repo.get_pull(number).create_issue_comment(body)

    def submit_review(self, number, event, body):
        self.repo.get_pull(number).create_review(event=event, body=body)

    def find_merged_branches(self):
        pulls = self.repo.get_pulls(state='closed')
        return [p.head.ref for p in pulls if p.merged]

    def delete_remote_branch(self, branch_name):
        self.repo.get_git_ref(f"heads/{branch_name}").delete()

# GitLab Implementation
class GitLabForge(Forge):
    def __init__(self, token, base_url, repo_slug):
        if "api.github.com" in base_url: base_url = "https://gitlab.com"
        self.gl = gitlab.Gitlab(url=base_url, private_token=token)
        self.gl.auth()
        try:
            self.project = self.gl.projects.get(repo_slug)
        except:
            raise ValueError(f"Project {repo_slug} not found on GitLab")

    def get_user(self):
        return self.gl.user.username

    def create_pr(self, title, body, source, target, draft):
        title = f"Draft: {title}" if draft else title
        mr = self.project.mergerequests.create({
            'source_branch': source, 'target_branch': target, 
            'title': title, 'description': body
        })
        return StandardPR(mr, "gitlab")

    def get_pr(self, number):
        return StandardPR(self.project.mergerequests.get(number), "gitlab")

    def get_files(self, number):
        changes = self.project.mergerequests.get(number).changes()
        files = []
        for change in changes['changes']:
            patch = change['diff']
            files.append(FileDiff(
                filename=change['new_path'],
                status="modified" if not change['new_file'] else "added",
                additions=patch.count('\n+'), deletions=patch.count('\n-'),
                patch=patch
            ))
        return files

    def edit_pr(self, number, title=None, body=None):
        mr = self.project.mergerequests.get(number)
        if title: mr.title = title
        if body: mr.description = body
        mr.save()

    def comment(self, number, body):
        self.project.mergerequests.get(number).notes.create({'body': body})

    def submit_review(self, number, event, body):
        mr = self.project.mergerequests.get(number)
        if event == "APPROVE":
            try: mr.approve()
            except: pass 
            mr.notes.create({'body': f"✅ Approved: {body}"})
        else:
            prefix = "⛔ Requesting Changes: " if event == "REQUEST_CHANGES" else ""
            mr.notes.create({'body': f"{prefix}{body}"})

    def find_merged_branches(self):
        mrs = self.project.mergerequests.list(state='merged')
        return [mr.source_branch for mr in mrs]

    def delete_remote_branch(self, branch_name):
        self.project.branches.delete(branch_name)