import pytest

from ludwig.rules.expr import ExprError, NotChecked, compile_expr

CTX = {
    "width_mm": 1200.0,
    "height_mm": 2400.0,
    "depth_mm": None,
    "mark": "K01",
    "quantity": 4,
    "props.glazing_type": "HR++",
    "props.fire_rating_min": 30.0,
    "props.is_external": True,
    "limits.sash.max_width_mm": 1500.0,
    "parent.width_mm": 2400.0,
}


def ev(text, ctx=CTX):
    return compile_expr(text).evaluate(lambda name: ctx[name]).value


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 + 2", 3.0),
        ("3 + 0", 3.0),
        ("10 - 4 - 3", 3.0),
        ("2 * 3 + 4", 10.0),
        ("2 + 3 * 4", 14.0),
        ("(2 + 3) * 4", 20.0),
        ("9 / 2", 4.5),
        ("-width_mm", -1200.0),
        ("- -3", 3.0),
        ("width_mm == 1200", True),
        ("width_mm != 1200", False),
        ("width_mm < 1200", False),
        ("width_mm <= 1200", True),
        ("width_mm > 1199.5", True),
        ("width_mm >= 1201", False),
        ("mark == \"K01\"", True),
        ("mark < \"K02\"", True),
        ("true and false", False),
        ("true or false", True),
        ("not true", False),
        ("not width_mm > 2000", True),
        ("width_mm > 1000 and height_mm > 2000", True),
        ("width_mm > 2000 or height_mm > 2000", True),
        ("props.glazing_type in [\"HR++\", \"HR+++\"]", True),
        ("props.glazing_type in [\"enkel\"]", False),
        ("props.fire_rating_min in [30, 60]", True),
        ("quantity in [\"4\"]", False),
        ("abs(0 - 5)", 5.0),
        ("min(width_mm, height_mm)", 1200.0),
        ("max(width_mm, height_mm)", 2400.0),
        ("is_set(depth_mm)", False),
        ("is_set(width_mm)", True),
        ("width_mm <= limits.sash.max_width_mm", True),
        ("parent.width_mm - width_mm", 1200.0),
        ("props.is_external == true", True),
        ("\"a \\\"q\\\" b\" == \"a \\\"q\\\" b\"", True),
    ],
)
def test_operators(text, expected):
    assert ev(text) == expected


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("depth_mm > 0", "depth_mm is not set"),
        ("depth_mm + 1", "depth_mm is not set"),
        ("width_mm > 0 and depth_mm > 0", "depth_mm is not set"),
        ("not depth_mm > 0", "depth_mm is not set"),
        ("abs(depth_mm)", "depth_mm is not set"),
        ("depth_mm in [1, 2]", "depth_mm is not set"),
        ("mark > 3", "cannot compare text 'K01' with number 3.0"),
        ("mark == 3", "cannot compare text 'K01' with number 3.0"),
        ("mark + 1", "'+' needs a number, got text 'K01'"),
        ("width_mm and true", "'and' needs true/false, got number 1200.0"),
        ("width_mm / 0", "division by zero"),
        ("true < false", "cannot compare true/false True with true/false False"),
    ],
)
def test_missing_or_unusable_values_are_not_checked(text, reason):
    assert ev(text) == NotChecked(reason)


def test_is_set_reads_none_without_not_checked():
    assert ev("is_set(depth_mm) or width_mm > 0") is True
    assert ev("not is_set(depth_mm)") is True


def test_and_or_stop_early_so_guards_work():
    assert ev("is_set(depth_mm) and depth_mm > 100") is False
    assert ev("not is_set(depth_mm) or depth_mm > 100") is True
    assert ev("width_mm > 0 or depth_mm > 0") is True


def test_names_and_used_are_reported():
    expr = compile_expr("width_mm <= limits.sash.max_width_mm and is_set(depth_mm)")
    assert expr.names == {"width_mm", "limits.sash.max_width_mm", "depth_mm"}
    result = expr.evaluate(lambda n: CTX[n])
    assert result.used == ["width_mm", "limits.sash.max_width_mm", "depth_mm"]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "1 +",
        "(1 + 2",
        "1 + 2)",
        "width_mm = 3",
        "width_mm == ",
        "1 < 2 < 3",
        "1 < 2 in [true]",
        "__import__(\"os\")",
        "open(\"x\")",
        "props.x()",
        "width_mm.real()",
        "abs(1, 2)",
        "min(1)",
        "is_set(1)",
        "is_set(width_mm + 1)",
        "x if y else z",
        "x[0]",
        "[1, 2]",
        "lambda: 1",
        "a; b",
        "'single quotes'",
        "1e3",
        "x ** 2",
        "x % 2",
        "width_mm in []",
        "width_mm in [1,]",
        "true false",
        "and",
        "a.b.",
        "@x",
    ],
)
def test_anything_outside_the_grammar_is_rejected(text):
    with pytest.raises(ExprError):
        compile_expr(text)


def test_error_reports_the_column():
    with pytest.raises(ExprError, match="column 10"):
        compile_expr("width_mm = 3")
