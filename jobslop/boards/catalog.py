"""The boards that come with the app itself. Everything else comes from plugins."""

from jobslop.boards import jobspy, linkedin, ziprecruiter
from jobslop.boards.base import Board


def core_boards() -> list[Board]:
    return [*linkedin.BOARDS, *jobspy.BOARDS, *ziprecruiter.BOARDS]
