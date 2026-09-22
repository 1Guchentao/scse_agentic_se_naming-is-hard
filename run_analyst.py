import os, json
from analyst_agent import run_analyst


def main():
    f = open("brief.txt", "r", encoding="utf-8")
    brief_text = f.read()
    f.close()

    reqs = run_analyst(brief_text)

    if reqs:
        if not os.path.exists("artifacts"):
            os.makedirs("artifacts")
        json.dump(reqs, open("artifacts/requirements.json", "w", encoding="utf-8"), indent=4)
        print("saved to artifacts/requirements.json")
    else:
        print("failed to get requirements")


if __name__ == "__main__":
    main()