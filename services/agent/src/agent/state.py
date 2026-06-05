from typing import List, Optional, TypedDict


class ReviewIssue(TypedDict):
    """审核发现的问题"""
    category: str
    severity: str
    description: str
    file_path: str
    fix_suggestion: str


class ReviewState(TypedDict):
    """审核状态"""
    project_info: dict
    file_content: str
    file_type: str
    issues: List[ReviewIssue]
    fixed_content: Optional[str]
    suggestions: List[str]
    status: str
    round: int
    max_rounds: int
