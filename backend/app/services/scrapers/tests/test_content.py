"""Tests for content.py — pure text logic."""

from app.services.scrapers.content import (
    cert_headings,
    clean_markdown,
    is_track_link,
    needs_section,
    normalize,
    prepare_catalog_text,
    sanitize,
    sections,
    text_hash,
    validate,
)

CHROME = (
    "UT Dallas 2025 Undergraduate Catalog\n"
    "Download page as a PDF, opens a new tab\n"
    "Download page as a DOCX (MS Word) file\n"
    "Open page in a printable window, opens a new tab\n"
    "Compare Versions\n"
)

COMBINED = (
    CHROME
    + "Example School of Arts\n"
    + "Certificates\n"
    + "Certificate in Alpha Studies\n"
    + "Certificate in Beta Studies\n\n\n"
    + "Certificate in Alpha Studies\n\n6 semester credit hours\n\nAlpha requires ALPHA 1301 and ALPHA 2302.\n\n"
    + "Certificate in Beta Studies\n\n9 semester credit hours\n\nBeta requires BETA 1301 and BETA 2302.\n\n"
    + "Updated: 2025-09-04 16:19:56 v13.4a4822"
)

DEGREE_COPY = (
    CHROME
    + "School of Natural Sciences\nPhysics (BA)\n\nDegree text about physics.\n\n"
    + "Certificates\nCertificate in Quantum Stuff\n\n15 semester credit hours\n\nQuantum requires PHYS 4340.\n"
)

SINGLE = (
    CHROME
    + "Naveen Jindal School of Management\nCertificates\n"
    + "Certificate in Innovation\n\n9 semester credit hours\n\nInnovation requires ENTP 3301.\n"
)


def test_sanitize_matches_folder_names():
    assert sanitize("BA in Education - 4-8 Science") == "ba_in_education_4_8_science"
    assert sanitize("Certificate in Holocaust, Genocide, and Human Rights") == "certificate_in_holocaust_genocide_and_human_rights"
    assert sanitize("Certificate in User Experience (UX) Research") == "certificate_in_user_experience_ux_research"


def test_hash_ignores_updated_stamp_and_whitespace():
    a = "Core courses\n\nCS 1337   Computer Science I\nUpdated: 2025-08-04 08:26:12 v12.c30585"
    b = "Core courses\n\nCS 1337 Computer Science I\nUpdated: 2026-01-01 00:00:00 v99.zzzzzz"
    assert text_hash(a) == text_hash(b)


def test_hash_changes_when_content_changes():
    assert text_hash("CS 1337 Computer Science I") != text_hash("CS 1338 Computer Science II")


def test_normalize_collapses_blank_lines():
    assert normalize("a\n\n\n\nb  c") == "a\n\nb c"


def test_validate():
    long_text = "word " * 40
    assert validate(long_text, 200) is None
    assert validate(long_text, 404) == "HTTP 404"
    assert validate("The University of Texas at Dallas | Privacy Policy", 200).startswith("too short")
    assert validate(None, 200).startswith("too short")


def test_cert_headings_skip_table_of_contents():
    heads = cert_headings(COMBINED.splitlines())
    assert [t for _i, t in heads] == ["Certificate in Alpha Studies", "Certificate in Beta Studies"]


def test_needs_section():
    assert needs_section(COMBINED) is True
    assert needs_section(DEGREE_COPY) is True
    assert needs_section(SINGLE) is False


def test_sections_split_a_combined_page():
    found = dict(sections(COMBINED))
    assert set(found) == {"certificate_in_alpha_studies", "certificate_in_beta_studies"}
    alpha = found["certificate_in_alpha_studies"]
    assert "ALPHA 1301" in alpha and "BETA 1301" not in alpha
    assert "Example School of Arts" in alpha
    assert "Updated:" not in found["certificate_in_beta_studies"]


def test_section_from_a_degree_page_copy_drops_the_degree_text():
    text, err = prepare_catalog_text("certificate_in_quantum_stuff", DEGREE_COPY)
    assert err is None
    assert "PHYS 4340" in text and "Degree text about physics" not in text


def test_prepare_missing_section_is_an_error():
    text, err = prepare_catalog_text("certificate_in_gamma_studies", COMBINED)
    assert text is None and "no certificate section" in err


def test_prepare_leaves_other_pages_whole():
    text, err = prepare_catalog_text("certificate_in_innovation", SINGLE)
    assert err is None and text == SINGLE.strip()
    text, err = prepare_catalog_text("bachelor_of_science_in_computer_science", "CS degree text " * 5)
    assert err is None and text.startswith("CS degree text")


def test_clean_markdown_strips_nav_footer_and_links():
    md = (
        "[Skip](https://x/#main)\n"
        "  * [Students](https://x/students/)\n"
        "# Tuition Rates\n"
        "See [the bursar](https://x/bursar \"Bursar\") for details.\n"
        "Email: bursar@utdallas.edu\n"
        "[Privacy Policy](https://x/privacy/)\n"
        "![](https://tracker/pixel)\n"
    )
    out = clean_markdown(md)
    assert out.startswith("# Tuition Rates")
    assert "See the bursar for details." in out
    assert "Students" not in out and "Privacy" not in out and "pixel" not in out


def test_track_links_are_recognised():
    assert is_track_link("BA in Education - EC-6 Core Subjects")
    assert is_track_link("BS in Education - 4-8 Mathematics")
    assert is_track_link("BA in Media Arts and Design - Critical Media Studies Concentration")
    assert not is_track_link("Bachelor of Arts in Education")
    assert not is_track_link("Certificate in Cyber Defense")
    assert not is_track_link("Undergraduate Minors")
