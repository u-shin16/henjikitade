"""Repositoryの取得窓口。

MOCK_MODE時はメモリ上のモックRepositoryを、
通常時はFirestoreへ接続するRepositoryを返す。
呼び出し側はどちらでも同じインターフェースで使用できる。
"""
from flask import current_app

_mock_repos = None
_real_repos = None


def get_repositories():
    """(UserRepository, ManagedFormRepository, FormResponseRepository) を返す。"""
    global _mock_repos, _real_repos

    if current_app.config.get("MOCK_MODE"):
        if _mock_repos is None:
            from app.mock.mock_data import build_mock_store
            from app.mock.mock_repository import (
                MockFormResponseRepository,
                MockManagedFormRepository,
                MockUserRepository,
            )

            store = build_mock_store()
            _mock_repos = (
                MockUserRepository(store),
                MockManagedFormRepository(store),
                MockFormResponseRepository(store),
            )
        return _mock_repos

    if _real_repos is None:
        from .form_repository import ManagedFormRepository
        from .response_repository import FormResponseRepository
        from .user_repository import UserRepository

        _real_repos = (
            UserRepository(),
            ManagedFormRepository(),
            FormResponseRepository(),
        )
    return _real_repos
