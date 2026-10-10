"""Observe the unmodified teacher simulation and save its actual frames."""

import json
from pathlib import Path
import runpy
import sys


def main():
    import irsim
    import matplotlib
    matplotlib.use("Agg", force=True)
    import numpy as np
    from PIL import Image

    script, world = sys.argv[1:3]
    original_make = irsim.make

    def observed_make(*args, **kwargs):
        kwargs["display"] = False
        env = original_make(*args, **kwargs)
        robot = env.robot_list[0]
        goal = [float(robot.goal[0, 0]), float(robot.goal[1, 0])]
        poses, frames = [], []
        step, render, end = env.step, env.render, env.end

        def snapshot():
            poses.append({"pose": [float(value) for value in robot.state[:, 0]],
                          "collision": bool(robot.collision)})

        def frame():
            figure = env._env_plot.ax.figure
            figure.canvas.draw()
            image = Image.fromarray(np.asarray(figure.canvas.buffer_rgba())).convert("RGB")
            image.thumbnail((600, 600))
            frames.append(image.copy())

        def observed_step(*values, **options):
            result = step(*values, **options)
            snapshot()
            return result

        def observed_render(*values, **options):
            result = render(*values, **options)
            if (len(poses) - 1) % 6 == 0:
                frame()
            return result

        def observed_end(*values, **options):
            frame()
            env._env_plot.ax.figure.savefig("route.png", dpi=110)
            frames[0].save("route.gif", save_all=True, append_images=frames[1:],
                           duration=120, loop=0)
            Path("capture.json").write_text(json.dumps(
                {"goal": goal, "poses": poses, "frames": len(frames),
                 "collision_observed": any(row["collision"] for row in poses)},
                indent=2), encoding="utf-8")
            return end(*values, **options)

        snapshot()
        frame()
        env.step, env.render, env.end = observed_step, observed_render, observed_end
        return env

    irsim.make = observed_make
    sys.path.insert(0, str(Path.cwd()))
    sys.argv = [script, world]
    try:
        runpy.run_path(script, run_name="__main__")
    finally:
        irsim.make = original_make


if __name__ == "__main__":
    main()
