from selfauditbench.core.sanitize import sanitize_payload, strip_hidden_reasoning


def test_strips_asb_thinking_but_preserves_action() -> None:
    raw = "[Thinking]: secret plan\n[Action]: I will call the lookup with the params as None"
    visible = strip_hidden_reasoning(raw)
    assert "secret plan" not in visible
    assert "[Action]" in visible


def test_strips_converse_scratchpad_recursively() -> None:
    raw = {"message": "<scratch_pad>private reasoning</scratch_pad>Public request"}
    visible = sanitize_payload(raw)
    assert "private reasoning" not in visible["message"]
    assert "Public request" in visible["message"]

