import json
import sys

try:
    import dashscope
    from dashscope import Generation
except ModuleNotFoundError:
    print("dashscope not installed, run pip install dashscope first")
    sys.exit(1)


def validate_requirements(data):
    if type(data) != dict:
        return False
    required = ["goal", "allowed_actions", "safe_stop", "avoid_obstacles"]
    for k in required:
        if k not in data:
            return False
    if type(data["goal"]) != str:
        return False
    if type(data["allowed_actions"]) != list:
        return False
    if data["safe_stop"] not in [True, False] or data["avoid_obstacles"] not in [True, False]:
        return False
    for a in data["allowed_actions"]:
        if a not in ["FORWARD", "LEFT", "RIGHT", "STOP"]:
            return False
    # check no extra keys
    for k in data.keys():
        if k not in required:
            return False
    return True


def run_analyst(brief_text):
    dashscope.api_key = "sk-ws-H.PIELXDY.knWg.MEYCIQCxER2675-_MH5ApknrtoY0LtI5M-LnbD9zmc4IPFUfpQIhALv_54ivbnC1IaEpmM2Ch0v6s059ViFUY7CyLb-ICBY4"

    prompt = """ #AI
 Convert the text below into JSON.
Only output JSON, no explanation. allowed_actions must be from FORWARD, LEFT, RIGHT, STOP.
Format: {"goal": "...", "allowed_actions": [...], "safe_stop": true, "avoid_obstacles": true}"""

    print("calling qwen...")
    resp = Generation.call(
        model="qwen-turbo",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": brief_text}
        ],
        result_format='message'
    )

    raw = resp.output.choices[0].message.content.strip()
    req_data = json.loads(raw)

    if validate_requirements(req_data):
        print("validation ok")
        return req_data
    else:
        print("validation failed, got:", raw)
        return None


