"""Tests for the open-source license map."""

from backend.services.licenses import find_licenses, render_licenses_markdown

# Minimal but distinctive snippets of each license's wording.
MIT_TEXT = (
    "MIT License\n\nCopyright (c) 2024 Foo\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    'of this software and associated documentation files (the "Software"), to deal\n'
)
APACHE_TEXT = "Apache License\nVersion 2.0, January 2004\nhttp://www.apache.org/licenses/\n"
GPL3_TEXT = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\nEveryone is permitted\n"
GPL2_TEXT = "GNU GENERAL PUBLIC LICENSE\nVersion 2, June 1991\nEveryone is permitted\n"
AGPL3_TEXT = "GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007\n"
LGPL3_TEXT = "GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n"
BSD3_TEXT = (
    "Redistribution and use in source and binary forms, with or without\n"
    "modification, are permitted provided that the following conditions are met:\n"
    "3. Neither the name of the copyright holder nor the names of its contributors\n"
)
BSD2_TEXT = (
    "Redistribution and use in source and binary forms, with or without\n"
    "modification, are permitted provided that the following conditions are met:\n"
    "1. Redistributions of source code must retain the above copyright notice.\n"
)
ISC_TEXT = (
    "ISC License\n\nPermission to use, copy, modify, and/or distribute this software for any\n"
    "purpose with or without fee is hereby granted, provided that the above\n"
    "copyright notice and this permission notice appear in all copies.\n"
)
ZEROBSD_TEXT = (
    "Permission to use, copy, modify, and/or distribute this software for any purpose\n"
    'with or without fee is hereby granted.\n\nTHE SOFTWARE IS PROVIDED "AS IS".\n'
)
UNLICENSE_TEXT = "This is free and unencumbered software released into the public domain.\n"


def test_mit_license_file_detected_and_classified():
    result = find_licenses({"LICENSE": MIT_TEXT})
    assert result["primary"] == "MIT"
    assert result["primary_category"] == "permissive"
    assert result["total"] == 1
    found = result["found"][0]
    assert found["spdx"] == "MIT"
    assert found["source_kind"] == "license-file"
    assert found["name_zh"] == "MIT 许可证"


def test_gpl_variants_are_distinguished_by_version_and_flavour():
    assert find_licenses({"LICENSE": GPL3_TEXT})["primary"] == "GPL-3.0"
    assert find_licenses({"LICENSE": GPL2_TEXT})["primary"] == "GPL-2.0"
    # AFFERO / LESSER must win over the plain GPL signature they contain
    assert find_licenses({"LICENSE": AGPL3_TEXT})["primary"] == "AGPL-3.0"
    assert find_licenses({"LICENSE": LGPL3_TEXT})["primary"] == "LGPL-3.0"
    assert find_licenses({"LICENSE": AGPL3_TEXT})["primary_category"] == "network-copyleft"
    assert find_licenses({"LICENSE": GPL3_TEXT})["primary_category"] == "strong-copyleft"


def test_bsd_three_vs_two_clause():
    assert find_licenses({"LICENSE": BSD3_TEXT})["primary"] == "BSD-3-Clause"
    assert find_licenses({"LICENSE": BSD2_TEXT})["primary"] == "BSD-2-Clause"


def test_isc_is_not_swallowed_by_zero_bsd():
    # ISC has the "provided that" clause; 0BSD drops it.
    assert find_licenses({"LICENSE": ISC_TEXT})["primary"] == "ISC"
    assert find_licenses({"LICENSE": ZEROBSD_TEXT})["primary"] == "0BSD"
    assert find_licenses({"LICENSE": ZEROBSD_TEXT})["primary_category"] == "public-domain"


def test_apache_and_unlicense():
    assert find_licenses({"LICENSE.txt": APACHE_TEXT})["primary"] == "Apache-2.0"
    assert find_licenses({"UNLICENSE": UNLICENSE_TEXT})["primary"] == "Unlicense"


def test_package_json_license_field():
    result = find_licenses({"package.json": '{\n  "name": "x",\n  "license": "MIT"\n}\n'})
    assert result["primary"] == "MIT"
    assert result["found"][0]["source_kind"] == "manifest"


def test_package_json_license_object_form():
    pkg = '{\n  "name": "x",\n  "license": { "type": "Apache-2.0", "url": "..." }\n}\n'
    assert find_licenses({"package.json": pkg})["primary"] == "Apache-2.0"


def test_pyproject_string_and_table_forms():
    assert (
        find_licenses({"pyproject.toml": 'license = "GPL-3.0-or-later"\n'})["primary"] == "GPL-3.0"
    )
    table = '[project]\nname = "x"\nlicense = { text = "MIT" }\n'
    assert find_licenses({"pyproject.toml": table})["primary"] == "MIT"


def test_trove_classifier_and_setup_cfg_with_comment():
    py = 'classifiers = [\n    "License :: OSI Approved :: MIT License",\n]\n'
    assert find_licenses({"pyproject.toml": py})["primary"] == "MIT"
    cfg = "[metadata]\nlicense = BSD-3-Clause  # the project license\n"
    assert find_licenses({"setup.cfg": cfg})["primary"] == "BSD-3-Clause"


def test_spdx_tag_in_source_file():
    result = find_licenses({"src/app.py": "# SPDX-License-Identifier: Apache-2.0\nx = 1\n"})
    assert result["primary"] == "Apache-2.0"
    assert result["found"][0]["source_kind"] == "spdx-tag"
    assert result["found"][0]["line"] == 1


def test_license_file_beats_manifest_as_primary():
    result = find_licenses({"LICENSE": MIT_TEXT, "pyproject.toml": 'license = "GPL-3.0"\n'})
    # both are recognised, but the LICENSE file is the authoritative primary
    assert result["primary"] == "MIT"
    assert result["total"] == 2
    kinds = {f["source_kind"] for f in result["found"]}
    assert kinds == {"license-file", "manifest"}


def test_unrecognised_license_file_is_unknown_not_silent():
    result = find_licenses({"LICENSE": "Acme Corp Proprietary License. All rights reserved.\n"})
    assert result["primary"] == "unknown"
    assert result["total"] == 0
    assert result["found"][0]["spdx"] == "unknown"


def test_no_license_found_warns_about_all_rights_reserved():
    result = find_licenses({"src/app.py": "print('hi')\n"})
    assert result["primary"] == ""
    assert result["found"] == []
    assert any("保留所有权利" in n for n in result["notes"])


def test_duplicate_license_across_sources_dedupes_total():
    pyproject = 'license = "MIT"\nclassifiers = ["License :: OSI Approved :: MIT License"]\n'
    result = find_licenses({"pyproject.toml": pyproject})
    assert result["primary"] == "MIT"
    assert result["total"] == 1  # one distinct license, even though two declarations


def test_categories_come_back_in_display_order():
    result = find_licenses({"LICENSE": AGPL3_TEXT, "pyproject.toml": 'license = "MIT"\n'})
    # permissive sorts before network-copyleft in the fixed family order
    assert result["categories"] == ["permissive", "network-copyleft"]


def test_markdown_render_permissive():
    md = render_licenses_markdown("Proj", find_licenses({"LICENSE": MIT_TEXT}))
    assert "# Proj — 开源许可证：你能不能用、能不能商用" in md
    assert "## 主许可证：MIT 许可证（宽松型）" in md
    assert "- 能不能商用：可以" in md
    assert "`LICENSE` — MIT 许可证（来自许可证文件）" in md


def test_markdown_render_no_license_warning():
    md = render_licenses_markdown("Proj", find_licenses({"src/app.py": "x = 1\n"}))
    assert "## ⚠ 没找到许可证" in md
    assert "保留所有权利" in md


def test_markdown_render_empty_and_none():
    assert render_licenses_markdown("Proj", None) == ""
    assert render_licenses_markdown("Proj", {}) == ""
