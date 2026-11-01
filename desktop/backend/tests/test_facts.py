from app.facts import check_facts


def test_rejects_negation_wording_change_conservatively():
    result = check_facts("项目可能在10月31日前不能上线，完成率是80%。", "项目未必能在10月31日前上线，完成率是80%。")
    # This conservative sample deliberately changes negation wording and must fall back.
    assert not result.accepted
    assert result.missing


def test_rejects_missing_number_and_negation():
    result = check_facts("预算不超过500元，不能自动充值。", "预算充足，可以充值。")
    assert not result.accepted
    assert any("500" in item for item in result.missing)
    assert any("negation" in item for item in result.missing + result.introduced)


def test_rejects_new_number():
    result = check_facts("准备三段音频。", "准备四段音频。")
    assert not result.accepted


def test_accepts_conservative_filter():
    result = check_facts("嗯，我们周五之前提交3份报告。", "我们周五之前提交3份报告。")
    assert result.accepted, result.warnings


def test_strong_filter_allows_removed_noise_and_greek_normalization():
    result = check_facts(
        "之后大家学习热情高涨。体积功是P外乘以德尔塔 V。",
        "体积功是P外 × ΔV。做功只与P外和ΔV有关。",
        {"number", "latin", "scope"},
    )
    assert result.accepted, result.warnings


def test_strong_filter_still_rejects_undefined_new_formula_variable():
    result = check_facts(
        "体积功是P外乘以delta V。",
        "体积功是P外 × ΔV，W 会变化。",
        {"number", "latin", "scope"},
    )
    assert not result.accepted
    assert any("latin:W" in item for item in result.introduced)


def test_strong_filter_accepts_explicitly_defined_formula_variable():
    result = check_facts(
        "体积功是P外乘以delta V。",
        "体积功为 W = P外 × ΔV。",
        {"number", "latin", "scope"},
    )
    assert result.accepted, result.warnings


def test_accepts_spaced_formula_variable_and_removed_indefinite_yi():
    result = check_facts(
        "我们从一个整体考虑，W e等于负的P外乘以delta V。",
        "从整体考虑，We等于负的P外乘以ΔV。",
    )
    assert result.accepted, result.warnings
