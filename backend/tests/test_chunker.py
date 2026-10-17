from app.services.chunker import chunk_parsed_sections


def test_chunker_preserves_pages_sections_and_hashes() -> None:
    sections = [
        {"page": 3, "section": "Leave", "text": "Employees may request annual leave."},
        {"page": 4, "section": "Security", "text": "Multi-factor authentication is required."},
    ]

    chunks = chunk_parsed_sections(sections)

    assert [(chunk.page, chunk.section) for chunk in chunks] == [
        (3, "Leave"),
        (4, "Security"),
    ]
    assert chunks[0].chunk_hash == chunk_parsed_sections(sections)[0].chunk_hash
    assert chunks[0].token_estimate > 0


def test_large_text_is_split_with_overlap_without_crossing_page() -> None:
    sentence = " ".join(f"word{index}" for index in range(100)) + "."
    text = " ".join(sentence for _ in range(8))

    chunks = chunk_parsed_sections(
        [
            {"page": 7, "section": "Operations", "text": text},
            {"page": 8, "section": "Safety", "text": "Safety rules apply."},
        ]
    )

    page_seven_chunks = [chunk for chunk in chunks if chunk.page == 7]
    assert len(page_seven_chunks) > 1
    assert all(chunk.token_estimate <= 600 for chunk in page_seven_chunks)
    assert page_seven_chunks[0].text.split()[-45:] == page_seven_chunks[1].text.split()[:45]
    assert all(chunk.page == 7 and chunk.section == "Operations" for chunk in page_seven_chunks)
    assert chunks[-1].page == 8
