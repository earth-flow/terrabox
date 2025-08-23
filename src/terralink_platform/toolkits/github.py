"""GitHub toolkit plugin for the Terralink platform.

This module provides GitHub-related tools that can interact with
GitHub repositories and issues using GitHub Token authentication
and the PyGithub library.
"""

from typing import Any, Dict, Optional
from github import Github

from ..models import ToolSpec


def _gh_sample_repos(username: str) -> list[str]:
    """Return a deterministic list of sample repositories for a user.

    In lieu of real GitHub API calls this helper produces a
    predictable set of repository names based on the input
    ``username``.  Each user will have up to three repos whose
    names incorporate the username.
    """
    base = username.strip().lower() or "default"
    return [f"{base}-repo-{n}" for n in range(1, 4)]


async def list_user_repos_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handler for listing GitHub user repositories.
    
    Parameters
    ----------
    arguments : Dict[str, Any]
        Tool arguments containing 'username' and 'github_token'
    context : Dict[str, Any]
        Execution context
        
    Returns
    -------
    Dict[str, Any]
        Dictionary containing list of repositories
    """
    username = arguments.get("username")
    github_token = arguments.get("github_token")
    
    if not username:
        raise ValueError("Username is required")
    
    try:
        # 使用PyGithub库连接GitHub
        if github_token:
            g = Github(github_token)
        else:
            # 如果没有token，使用公开API（有限制）
            g = Github()
        
        # 获取用户对象
        user = g.get_user(username)
        
        # 获取用户的仓库列表
        repos = user.get_repos(sort="updated", direction="desc")
        
        repositories = []
        # 限制返回30个仓库
        for i, repo in enumerate(repos):
            if i >= 30:
                break
            repositories.append({
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description,
                "private": repo.private,
                "url": repo.html_url,
                "language": repo.language,
                "stars": repo.stargazers_count,
                "forks": repo.forks_count
            })
        
        return {"repositories": repositories}
        
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise ValueError(f"User '{username}' not found")
        elif "401" in str(e) or "Bad credentials" in str(e):
            raise ValueError("Invalid GitHub token")
        elif "403" in str(e) or "rate limit" in str(e).lower():
            raise ValueError("GitHub API rate limit exceeded. Please provide a valid GitHub token.")
        else:
            raise ValueError(f"GitHub API error: {str(e)}")


async def create_issue_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handler for creating GitHub issues.
    
    Parameters
    ----------
    arguments : Dict[str, Any]
        Tool arguments containing 'repository', 'title', 'github_token', and optional 'body'
    context : Dict[str, Any]
        Execution context
        
    Returns
    -------
    Dict[str, Any]
        Dictionary containing created issue information
        
    Raises
    ------
    ValueError
        If required parameters are missing or invalid
    """
    repository = arguments.get("repository")
    title = arguments.get("title")
    body = arguments.get("body", "")
    github_token = arguments.get("github_token")
    
    if not repository:
        raise ValueError("Repository is required")
    if not title:
        raise ValueError("Title is required")
    if not github_token:
        raise ValueError("GitHub token is required")
    
    # 解析仓库名称（格式：owner/repo）
    if "/" not in repository:
        raise ValueError("Repository must be in format 'owner/repo'")
    
    try:
        # 使用PyGithub库连接GitHub
        g = Github(github_token)
        
        # 获取仓库对象
        repo = g.get_repo(repository)
        
        # 创建issue
        issue = repo.create_issue(
            title=title,
            body=body
        )
        
        return {
            "repository": repository,
            "issue_number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "url": issue.html_url,
            "state": issue.state
        }
        
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise ValueError(f"Repository '{repository}' not found or no access")
        elif "401" in str(e) or "Bad credentials" in str(e):
            raise ValueError("Invalid GitHub token")
        elif "403" in str(e) or "Forbidden" in str(e):
            raise ValueError("Insufficient permissions to create issues in this repository")
        else:
            raise ValueError(f"GitHub API error: {str(e)}")


def setup(registrar):
    """Plugin setup function called by the platform.
    
    This function registers the GitHub toolkit and all its tools
    with the platform using the new plugin system.
    
    Parameters
    ----------
    registrar : Registrar
        The registrar instance provided by the platform
    """
    # Register the GitHub toolkit
    registrar.toolkit(
        name="github",
        description="Interact with GitHub resources such as repositories and issues",
        version="1.0"
    )
    
    # Register the list user repos tool
    list_repos_spec = ToolSpec(
        slug="github.list_user_repos",
        description="List repositories owned by a user",
        parameters={
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "GitHub username whose repositories to list",
                },
                "github_token": {
                    "type": "string",
                    "description": "GitHub personal access token (optional, but recommended to avoid rate limits)",
                }
            },
            "required": ["username"],
        },
        toolkit="github",
        requires_connection=False,
    )
    registrar.tool(list_repos_spec, list_user_repos_handler)
    
    # Register the create issue tool
    create_issue_spec = ToolSpec(
        slug="github.create_issue",
        description="Create an issue in a GitHub repository",
        parameters={
            "type": "object",
            "properties": {
                "repository": {
                    "type": "string",
                    "description": "Repository where the issue will be created (format: owner/repo)",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the issue",
                },
                "body": {
                    "type": "string",
                    "description": "Issue body text (optional)",
                },
                "github_token": {
                    "type": "string",
                    "description": "GitHub personal access token (required for creating issues)",
                }
            },
            "required": ["repository", "title", "github_token"],
        },
        toolkit="github",
        requires_connection=False,
    )
    registrar.tool(create_issue_spec, create_issue_handler)