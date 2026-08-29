import json
import tempfile
from pathlib import Path

from codeagent.tools import build_default_registry
from codeagent.tools.bash_policy import PermissionDecision, evaluate_command


def test_policy():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ws"
        root.mkdir()

        def deny(cmd):
            r = evaluate_command(cmd, root)
            assert r.decision == PermissionDecision.DENY, (cmd, r)

        def allow(cmd):
            r = evaluate_command(cmd, root)
            assert r.decision == PermissionDecision.ALLOW, (cmd, r)

        def ask(cmd):
            r = evaluate_command(cmd, root)
            assert r.decision == PermissionDecision.ASK, (cmd, r)

        deny("rm -rf x")
        deny("echo a > f.txt")
        deny("cd ..")
        deny("pip install foo")
        allow("g++ hello.cpp -o hello.exe")
        allow("python hello.py")
        allow("git status")
        ask("make")
        ask("unknown-cmd")


def test_tools():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ws"
        root.mkdir()
        asked = []
        reg = build_default_registry(
            root, confirm_bash=lambda c, r: (asked.append(c) or True)
        )
        names = {s["function"]["name"] for s in reg.schemas()}
        assert "Bash" in names
        assert "AskUserQuestion" in names
        assert "TodoWrite" in names
        assert "NotebookEdit" in names

        out = reg.execute("Bash", {"command": "rm -rf x"})
        assert "拒绝" in out

        out = reg.execute("Bash", {"command": "dir"})
        assert "exit_code=" in out

        todos = json.dumps([{"id": "1", "content": "a", "status": "in_progress"}])
        assert "in_progress" in reg.execute("TodoWrite", {"todos": todos})

        nb = '{"cells":[],"nbformat":4,"nbformat_minor":5}'
        (root / "n.ipynb").write_text(nb)
        out = reg.execute(
            "NotebookEdit",
            {
                "path": "n.ipynb",
                "cell_idx": 0,
                "new_source": "print(1)",
                "is_new_cell": True,
            },
        )
        assert "插入" in out

        reg2 = build_default_registry(
            root, ask_user=lambda q, o, m: "yes"
        )
        out = reg2.execute("AskUserQuestion", {"question": "ok?"})
        assert "用户回答" in out


if __name__ == "__main__":
    test_policy()
    test_tools()
    print("ALL OK")
