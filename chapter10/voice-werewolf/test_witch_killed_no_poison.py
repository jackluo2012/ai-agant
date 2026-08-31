# -*- coding: utf-8 -*-
"""女巫规则边界测试：被刀且未被救的女巫当夜不得使用毒药。"""

import pytest
from werewolf.game import Judge
from werewolf.agent import PlayerAgent
from werewolf.roles import Role, Faction


def test_witch_killed_by_wolves_cannot_use_poison_in_same_night():
    """已验证契约：Judge._witch_act 阻止当晚被狼人刀死且未被救的女巫使用毒药。

    锁定的缺陷：不允许已死亡的女巫在她死亡的夜晚毒死另一名玩家。
    """
    players = [
        PlayerAgent("P1", Role.WEREWOLF, offline=True),
        PlayerAgent("P2", Role.WEREWOLF, offline=True),
        PlayerAgent("P3", Role.SEER, offline=True),
        PlayerAgent("P4", Role.WITCH, offline=True),
        PlayerAgent("P5", Role.VILLAGER, offline=True),
    ]

    judge = Judge(players, seed=42)
    witch = judge.by_name("P4")

    # 覆写女巫的目标选择：若被询问用药，则尝试毒 P3
    witch._offline_choose_target = lambda candidates, allow_none: "P3"

    # 狼人击杀了 P4（女巫）
    killed = "P4"
    poisoned, saved = judge._witch_act(killed)

    assert saved is False
    assert poisoned is None, "被狼人刀死的女巫当夜不能使用毒药"
