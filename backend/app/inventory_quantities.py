"""Exact compatible-unit inventory arithmetic, independent of API modules.

Legacy numeric columns remain readable. Text sidecars retain conversion precision
in SQLite, whose NUMERIC affinity otherwise rounds Decimal values through float.
"""

from decimal import Decimal

D = Decimal
UNITS = {
    "mg": ("mass", D(".001")),
    "g": ("mass", D(1)),
    "kg": ("mass", D(1000)),
    "oz": ("mass", D("28.349523125")),
    "lb": ("mass", D("453.59237")),
    "mL": ("volume", D(1)),
    "L": ("volume", D(1000)),
    "us_fl_oz": ("volume", D("29.5735295625")),
    "us_cup": ("volume", D("236.5882365")),
    "count": ("count", D(1)),
    "each": ("count", D(1)),
    **{u: (u, D(1)) for u in ("plate", "print", "swab", "slant")},
}


def compatible(source, target):
    return source in UNITS and target in UNITS and UNITS[source][0] == UNITS[target][0]


def convert(quantity, source, target):
    if not compatible(source, target):
        raise ValueError(
            f"Incompatible units: {source} and {target}; weight and volume cannot be interchanged"
        )
    if quantity is None:
        return None
    return quantity * UNITS[source][1] / UNITS[target][1]


def canonical(unit):
    # Keep existing API units unchanged; normalize newly introduced units to
    # bases so every supported conversion has a terminating decimal debit.
    return {
        "mg": "g",
        "oz": "g",
        "lb": "g",
        "us_fl_oz": "mL",
        "us_cup": "mL",
        "each": "count",
    }.get(unit, unit)


def balance(item):
    return (
        D(item.available_exact) if item.available_exact is not None else item.available
    )


def exact(value):
    return (
        format(value, ".3f")
        if value == value.quantize(D(".001"))
        else format(value, "f").rstrip("0")
    )


def text_or_none(value):
    return exact(value) if value is not None else None
