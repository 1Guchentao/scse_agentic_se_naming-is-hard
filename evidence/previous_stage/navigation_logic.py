def navigate(obstacles, target=None):
    if target is not None and not obstacles[target]:
        return target
    for direction in ["FORWARD", "LEFT", "RIGHT"]:
        if not obstacles[direction]:
            return direction
    return "STOP"