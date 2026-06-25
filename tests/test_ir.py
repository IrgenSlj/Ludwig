"""IR spine tests — pure Python, no kernel/inference (the always-green gate)."""
import pytest

from ir import Element, NamedDim, Param, ProgramNode
from toolkit import box


def test_param_requires_unit():
    with pytest.raises(ValueError):
        Param("width", 80, unit="")
    assert Param("width", 80).unit == "mm"


def test_crystallization_clamps_and_is_scalar():
    # [H3]: through P0/P1 crystallization is a scalar only.
    assert Element(id="a", crystallization=2.0).crystallization == 1.0
    assert Element(id="b", crystallization=-1.0).crystallization == 0.0


def test_box_registers_named_dims_and_stays_lazy():
    b = box("bracket", 80, 40, 6)
    assert (b.dim("length"), b.dim("width"), b.dim("height")) == (80, 40, 6)
    assert all(isinstance(d, NamedDim) for d in b.manifest)
    # geometry handle exists but the kernel has not been touched
    assert b.geometry is not None and not b.geometry.built


def test_provenance_is_a_program_node():
    # [H2]: provenance resolves to a program node, never a kernel handle.
    b = box("bracket", 80, 40, 6)
    b.provenance = ProgramNode(node_id="bracket", source_span=(1, 12))
    assert isinstance(b.provenance, ProgramNode)
