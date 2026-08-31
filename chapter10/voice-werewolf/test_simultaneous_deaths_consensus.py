# -*- coding: utf-8 -*-
"""胜负判定边界测试：狼人与好人同时出局时必须判为「未决」。"""

import pytest
from werewolf.game import Judge
from werewolf.agent import PlayerAgent
from werewolf.roles import Role, Faction

def test_simultaneous_deaths_returns_undecided_faction():
    """已验证契约：全员同时出局时 Judge._check_winner 返回 Faction.UNDECIDED。

    锁定的缺陷：当存活好人数为 0 且狼人数为 0 时，不得误判为 Faction.GOOD。
    """
    # 构造玩家：1 狼人 + 1 女巫（好人）
    p_wolf = PlayerAgent("P1", Role.WEREWOLF, offline=True)
    p_witch = PlayerAgent("P2", Role.WITCH, offline=True)
    judge = Judge([p_wolf, p_witch])

    # 两名玩家都在夜晚阶段出局
    p_wolf.alive = False
    p_witch.alive = False

    # 好人全灭且狼人全灭时必须报告「未决」，而不是「好人胜」
    winner = judge._check_winner()
    assert winner == Faction.UNDECIDED
