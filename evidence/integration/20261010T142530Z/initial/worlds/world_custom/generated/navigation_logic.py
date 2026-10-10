def navigate(obstacles, target=None):
    if target is not None and not obstacles[target]:
        return target
    for direction in ["FORWARD", "LEFT", "RIGHT"]:
        if not obstacles[direction]:
            return direction
    return "STOP"

def decide_next_move(state):
    obstacles = {"FORWARD": state["front_blocked"], "LEFT": state["left_blocked"], "RIGHT": state["right_blocked"]}
    if state["goal_ahead"]:
        if not obstacles["FORWARD"]:
            return navigate(obstacles, "FORWARD")
    if state["goal_on_left"]:
        if not obstacles["LEFT"]:
            return navigate(obstacles, "LEFT")
    if state["goal_on_right"]:
        if not obstacles["RIGHT"]:
            return navigate(obstacles, "RIGHT")
    return navigate(obstacles)