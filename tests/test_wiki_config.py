def test_test_pages_defaults_to_linked_and_refuses_an_unknown_value(tmp_path) -> None:
    """@brief `wiki.test_pages`: linked (default) | all | none; anything else named."""
    from clew.wiki.config import load_wiki_config

    (tmp_path / ".clew.yaml").write_text("wiki:\n  title: T\n")
    assert load_wiki_config(tmp_path, None)[0].test_pages == "linked"
    (tmp_path / ".clew.yaml").write_text("wiki:\n  test_pages: some\n")
    config, problems = load_wiki_config(tmp_path, None)
    assert config.test_pages == "linked" and any("wiki.test_pages" in p for p in problems)
