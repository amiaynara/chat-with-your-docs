def test_openapi_schema_documents_the_expected_paths_and_tags(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()

    paths = schema["paths"]
    assert "/documents" in paths
    assert "/documents/{document_id}" in paths
    assert "/documents/{document_id}/retry" in paths
    assert "/chat/messages" in paths

    assert paths["/documents"]["post"]["tags"] == ["documents"]
    assert paths["/documents"]["get"]["tags"] == ["documents"]
    assert paths["/documents/{document_id}"]["delete"]["tags"] == ["documents"]
    assert paths["/documents/{document_id}/retry"]["post"]["tags"] == ["documents"]
    assert paths["/chat/messages"]["post"]["tags"] == ["chat"]
    assert paths["/chat/messages"]["get"]["tags"] == ["chat"]

    # Every documents/chat route has a summary — the contract this ticket exists to guarantee,
    # not just that the paths are present.
    for path in ("/documents", "/chat/messages"):
        for operation in paths[path].values():
            assert operation.get("summary")

    document_schema = schema["components"]["schemas"]["DocumentOut"]
    assert document_schema["properties"]["error_category"]["description"]


def test_docs_and_redoc_render(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
