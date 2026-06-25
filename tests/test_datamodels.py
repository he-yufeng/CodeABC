"""Tests for the data-model (data shape) map."""

from backend.services.datamodels import find_data_models, render_data_models_markdown


def test_dataclass_fields_with_types_and_defaults():
    src = """
from dataclasses import dataclass

@dataclass
class User:
    id: int
    name: str
    email: str = ""
"""
    result = find_data_models({"models.py": src})
    assert result["total"] == 1
    model = result["models"][0]
    assert model["name"] == "User"
    assert model["kind"] == "dataclass"
    assert model["path"] == "models.py"
    field_names = [f["name"] for f in model["fields"]]
    assert field_names == ["id", "name", "email"]
    by_name = {f["name"]: f for f in model["fields"]}
    assert by_name["id"]["type"] == "int"
    assert by_name["id"]["has_default"] is False
    assert by_name["email"]["type"] == "str"
    assert by_name["email"]["has_default"] is True


def test_dataclass_decorator_with_args_and_dotted_form():
    src = """
import dataclasses

@dataclasses.dataclass(frozen=True)
class Point:
    x: float
    y: float
"""
    result = find_data_models({"geo.py": src})
    assert result["total"] == 1
    assert result["models"][0]["kind"] == "dataclass"
    assert [f["name"] for f in result["models"][0]["fields"]] == ["x", "y"]


def test_pydantic_basemodel_detected_and_config_not_a_field():
    src = """
from pydantic import BaseModel

class Order(BaseModel):
    total: float
    items: list[str] = []
    model_config = {"extra": "forbid"}
"""
    result = find_data_models({"schemas.py": src})
    assert result["total"] == 1
    model = result["models"][0]
    assert model["kind"] == "pydantic"
    # model_config is a plain assignment, not an annotated field, so it must not
    # be listed among the data fields.
    assert [f["name"] for f in model["fields"]] == ["total", "items"]


def test_pydantic_dotted_base_form():
    src = """
import pydantic

class Account(pydantic.BaseModel):
    balance: int
"""
    result = find_data_models({"acct.py": src})
    assert result["total"] == 1
    assert result["models"][0]["kind"] == "pydantic"


def test_typeddict_and_namedtuple_class_forms():
    src = """
from typing import TypedDict, NamedTuple

class Movie(TypedDict):
    title: str
    year: int

class Coord(NamedTuple):
    lat: float
    lon: float
"""
    result = find_data_models({"types.py": src})
    kinds = {m["name"]: m["kind"] for m in result["models"]}
    assert kinds == {"Movie": "typeddict", "Coord": "namedtuple"}


def test_plain_class_is_not_a_data_model():
    src = """
class Service:
    base_url: str = "http://x"

    def run(self):
        return 1
"""
    # A plain class (no dataclass decorator, no model base) is not a declared
    # data shape, even if it has an annotated class attribute.
    assert find_data_models({"svc.py": src})["total"] == 0


def test_underscore_and_dunder_fields_skipped():
    src = """
from dataclasses import dataclass

@dataclass
class Row:
    __tablename__: str = "rows"
    _internal: int = 0
    value: int = 1
"""
    fields = find_data_models({"m.py": src})["models"][0]["fields"]
    assert [f["name"] for f in fields] == ["value"]


def test_syntax_error_file_skipped():
    good = "from dataclasses import dataclass\n\n@dataclass\nclass A:\n    x: int\n"
    bad = "def broken( :\n"
    result = find_data_models({"good.py": good, "bad.py": bad})
    assert result["total"] == 1
    assert result["models"][0]["name"] == "A"


def test_non_python_file_skipped():
    assert find_data_models({"data.json": '{"name": "x"}'})["total"] == 0


def test_kinds_listed_and_sorted_by_location():
    src_a = "from dataclasses import dataclass\n\n@dataclass\nclass Z:\n    a: int\n"
    src_b = "from pydantic import BaseModel\n\nclass Y(BaseModel):\n    b: int\n"
    result = find_data_models({"z.py": src_a, "y.py": src_b})
    assert result["kinds"] == ["dataclass", "pydantic"]
    # sorted by (path, line): y.py before z.py
    assert [m["name"] for m in result["models"]] == ["Y", "Z"]


def test_limit_caps_returned_models():
    contents = {
        f"m{i}.py": f"from dataclasses import dataclass\n\n@dataclass\nclass M{i}:\n    x: int\n"
        for i in range(5)
    }
    result = find_data_models(contents, limit=3)
    assert result["total"] == 5
    assert len(result["models"]) == 3


def test_render_markdown_empty_when_no_models():
    assert render_data_models_markdown("Proj", find_data_models({})) == ""
    assert render_data_models_markdown("Proj", None) == ""


def test_render_markdown_lists_models_and_fields():
    src = """
from dataclasses import dataclass

@dataclass
class User:
    id: int
    email: str = ""
"""
    md = render_data_models_markdown("Proj", find_data_models({"m.py": src}))
    assert "User" in md
    assert "id" in md
    assert "email" in md
    assert "dataclass" in md
