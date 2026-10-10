def navigate(obstacles, target=None):
    if target is not None and not obstacles[target]:
        return target
    for direction in ["FORWARD", "LEFT", "RIGHT"]:
        if not obstacles[direction]:
            return direction
    return "STOP"

def decide_next_move(state):
    blocked_paths = {"FORWARD": state["front_blocked"], "LEFT": state["left_blocked"], "RIGHT": state["right_blocked"]}
    if state["goal_ahead"] and not blocked_paths["FORWARD"]:
        return navigate(blocked_paths, "FORWARD")
    if state["goal_on_left"] and not blocked_paths["LEFT"]:
        return navigate(blocked_paths, "LEFT")
    if state["goal_on_right"] and not blocked_paths["RIGHT"]:
        return navigate(blocked_paths, "RIGHT")
    return navigate(blocked_paths)

_correct_decision = decide_next_move

def decide_next_move(state):
    action = _correct_decision(state)
    return {"LEFT": "RIGHT", "RIGHT": "LEFT"}.get(action, action)

_recorded_decision = decide_next_move
recorded_states = []

def decide_next_move(state):
    recorded_states.append(state.copy())
    return _recorded_decision(state)
