"""Parser parent relationships must survive normalization independently of geometry."""
from copy import deepcopy

from pdf_rules.mineru_layout import normalize_layout


def body(box):
    return {"type": "image_body", "bbox": list(box), "lines": []}


def caption():
    return {"type": "image_caption", "bbox": [10, 90, 210, 103],
            "lines": [{"bbox": [10, 90, 210, 103],
                       "spans": [{"content": "Figure 1.1 Comparison"}]}]}


def layouts():
    left, right, title = body((10, 20, 100, 80)), body((120, 20, 210, 80)), caption()
    shared = [{"page_idx": 0, "page_size": [600, 800], "para_blocks": [
        {"type": "image", "bbox": [10, 20, 210, 103], "blocks": [left, right, title]}]}]
    independent = [{"page_idx": 0, "page_size": [600, 800], "para_blocks": [
        {"type": "image", "bbox": [10, 20, 100, 80], "blocks": [deepcopy(left)]},
        {"type": "image", "bbox": [10, 20, 210, 103],
         "blocks": [deepcopy(right), deepcopy(title)]}]}]
    return shared, independent


def normalized(raw, first_page=1):
    return normalize_layout(raw, first_page, [(600, 800)])


def test_same_flat_boxes_from_different_parents_are_distinguishable():
    shared, independent = layouts()
    a, b = normalized(shared), normalized(independent)
    assert [(x.kind, x.bbox, x.text) for x in a] == [(x.kind, x.bbox, x.text) for x in b]
    assert a != b, "Two distinct parser object trees must not become identical flat evidence"


def test_two_panels_and_title_retain_one_actual_parent():
    shared, _ = layouts()
    objects = normalized(shared)
    assert len({x.parent_id for x in objects}) == 1
    assert all(x.parent_id for x in objects)
    assert len({x.source_id for x in objects}) == 3
    assert all(x.parent_bbox == (10, 20, 210, 103) for x in objects)
    assert all(x.parent_kind == "image" for x in objects)


def test_caption_does_not_inherit_an_independent_previous_parent():
    _, separate = layouts()
    left, right, title = normalized(separate)
    assert left.parent_id != right.parent_id
    assert right.parent_id == title.parent_id


def test_parent_coordinates_and_page_ids_use_original_pdf_frame():
    shared, _ = layouts()
    raw = deepcopy(shared)
    raw[0]["page_size"] = [300, 400]
    for block in raw[0]["para_blocks"]:
        block["bbox"] = [x / 2 for x in block["bbox"]]
        for child in block["blocks"]:
            child["bbox"] = [x / 2 for x in child["bbox"]]
            for line in child.get("lines", []):
                line["bbox"] = [x / 2 for x in line["bbox"]]
    objects = normalized(raw, 205)
    assert all(x.page_number == 205 for x in objects)
    assert all(x.parent_bbox == (10, 20, 210, 103) for x in objects)
    assert objects[0].parent_id != normalized(shared, 1)[0].parent_id


def test_duplicate_parent_shapes_keep_distinct_stable_ids():
    shared, _ = layouts()
    raw = deepcopy(shared)
    raw[0]["para_blocks"].append(deepcopy(raw[0]["para_blocks"][0]))
    a = normalized(raw)
    b = normalized(deepcopy(raw))
    assert a == b
    assert a[0].parent_id != a[3].parent_id


def test_standalone_block_has_source_but_no_invented_parent():
    raw = [{"page_idx": 0, "page_size": [600, 800],
            "para_blocks": [body((10, 20, 100, 80))]}]
    # A raw body is an observation, not a separate image parent inferred from distance.
    objects = normalized(raw)
    assert objects == []
    raw[0]["para_blocks"][0]["type"] = "image"
    obj = normalized(raw)[0]
    assert obj.source_id
    assert obj.parent_id is None
    assert obj.parent_bbox is None


def test_discarded_and_paragraph_paths_never_collide():
    shared, _ = layouts()
    raw = deepcopy(shared)
    raw[0]["discarded_blocks"] = deepcopy(raw[0]["para_blocks"])
    objects = normalized(raw)
    assert len({o.source_id for o in objects}) == len(objects)
    assert objects[0].parent_id != objects[3].parent_id
