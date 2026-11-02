"""The boards that come with the app itself."""

from jobslop.boards import country, jobspy, keyed, linkedin, remote, special, ziprecruiter
from jobslop.boards.base import Board


def core_boards() -> list[Board]:
    return [*linkedin.BOARDS, *jobspy.BOARDS, *ziprecruiter.BOARDS, *keyed.BOARDS, *country.BOARDS,
            *special.BOARDS, *remote.BOARDS]
