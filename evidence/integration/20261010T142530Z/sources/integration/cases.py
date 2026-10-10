"""Independent expected actions for the six boolean sensor inputs."""

from itertools import product

FIELDS = ("front_blocked", "left_blocked", "right_blocked",
          "goal_ahead", "goal_on_left", "goal_on_right")
MOVES = ("FORWARD", "LEFT", "RIGHT")
CLEAR_EXITS = (
    ("FORWARD", "LEFT", "RIGHT"), ("FORWARD", "LEFT"),
    ("FORWARD", "RIGHT"), ("FORWARD",),
    ("LEFT", "RIGHT"), ("LEFT",), ("RIGHT",), (),
)


def scenarios():
    for blocked_index, blocked in enumerate(product((False, True), repeat=3)):
        clear = CLEAR_EXITS[blocked_index]
        for goals in product((False, True), repeat=3):
            indicated = dict(zip(MOVES, goals))
            candidates = [move for move in clear if indicated[move]]
            expected = (candidates or list(clear) or ["STOP"])[0]
            yield dict(zip(FIELDS, blocked + goals)), expected
