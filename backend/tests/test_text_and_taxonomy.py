from rag.services.taxonomy import TreatmentTaxonomy, normalize_policy_type
from rag.services.text_processing import (
    content_terms,
    remove_repeated_boilerplate,
    repair_text,
    split_sentences,
    tokenize,
)


def test_split_sentences_keeps_currency_abbreviation_intact():
    sentences = split_sentences("Dental is limited to Rs. 10,000 per year. Cosmetic work is excluded.")
    assert sentences == ["Dental is limited to Rs. 10,000 per year.", "Cosmetic work is excluded."]


def test_split_sentences_keeps_header_lines_separate_but_joins_wrapped_lines():
    text = "Policy Type: Dental\nPolicy Version: 2026.1\nConsultations are reimbursable\nup to Rs. 5,000 per year."
    assert split_sentences(text) == [
        "Policy Type: Dental",
        "Policy Version: 2026.1",
        "Consultations are reimbursable up to Rs. 5,000 per year.",
    ]


def test_boilerplate_headers_and_page_numbers_are_removed():
    pages = [f"ACME HEALTH POLICY\nClause {index} text here.\nPage {index} of 3" for index in range(1, 4)]
    cleaned = remove_repeated_boilerplate(pages)
    assert all("ACME HEALTH POLICY" not in page for page in cleaned)
    assert all("Page" not in page for page in cleaned)
    assert "Clause 2 text here." in cleaned[1]


def test_repair_text_fixes_rupee_mojibake():
    assert repair_text("up to â\u0082„15,000") == "up to ₹15,000"
    assert repair_text("up to â‚¹15,000") == "up to ₹15,000"


def test_tokenize_and_content_terms():
    assert tokenize("Physiotherapy sessions") == ["physiotherapy", "session"]
    assert content_terms("Medical reimbursement for cosmetic procedures") == {"cosmetic"}


def test_taxonomy_resolves_synonyms_to_policy_categories():
    taxonomy = TreatmentTaxonomy()
    assert taxonomy.resolve("Root canal treatment") == "Dental"
    assert taxonomy.resolve("RCT") == "Dental"
    assert taxonomy.resolve("MRI scan") == "Diagnostics"
    assert taxonomy.resolve("Dental consultation") == "Dental"  # specific beats the OPD umbrella
    assert taxonomy.resolve("Prescription spectacles") == "Vision"
    assert taxonomy.resolve("Acupuncture") is None


def test_taxonomy_expansion_and_unknown_fallback():
    taxonomy = TreatmentTaxonomy()
    expanded = taxonomy.expand("Root canal")
    assert expanded[0] == "Root canal"
    assert "Dental" in expanded and "tooth" in expanded
    assert "acupuncture" in taxonomy.expand("Acupuncture therapy")


def test_normalize_policy_type_matches_ingestion_title_case():
    assert normalize_policy_type("  mental   wellness ") == "Mental Wellness"
    assert normalize_policy_type("OPD") == "Opd"
    assert normalize_policy_type(None) is None
