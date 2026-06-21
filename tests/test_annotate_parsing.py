from backend.routers.analyze import _coerce_annotation_list


def test_passes_through_a_plain_array():
    arr = [
        {"line_start": 1, "line_end": 1, "annotation": "a"},
        {"line_start": 2, "line_end": 3, "annotation": "b"},
    ]
    assert _coerce_annotation_list(arr) == arr


def test_unwraps_an_object_wrapped_array():
    # Models sometimes wrap the array in an object instead of returning it bare;
    # the annotations must be salvaged, not silently dropped to an empty file.
    wrapped = {"annotations": [{"line_start": 1, "line_end": 2, "annotation": "y"}]}
    assert _coerce_annotation_list(wrapped) == wrapped["annotations"]


def test_unwraps_under_any_key_name():
    wrapped = {"批注": [{"line_start": 5, "line_end": 5, "annotation": "z"}]}
    assert _coerce_annotation_list(wrapped) == wrapped["批注"]


def test_none_and_scalars_become_empty():
    assert _coerce_annotation_list(None) == []
    assert _coerce_annotation_list({}) == []
    assert _coerce_annotation_list({"note": "not a list"}) == []
