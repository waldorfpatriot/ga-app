defmodule GAWeb.CatalogControllerTest do
  use GAWeb.ConnCase, async: true

  test "reader catalog includes the complete library and download availability", %{conn: conn} do
    conn = get(conn, ~p"/api/catalog")
    works = json_response(conn, 200)["works"]

    assert length(works) > 300
    assert Enum.any?(works, &(&1["id"] == "ga-001" and is_binary(&1["content_path"])))

    assert Enum.any?(
             works,
             &(&1["state"] == "import_queue" and not Map.has_key?(&1, "content_path"))
           )
  end

  test "developer catalog exposes the full status overview", %{conn: conn} do
    conn = get(conn, ~p"/api/developer/catalog")
    payload = json_response(conn, 200)

    assert payload["audience"] == "developer"
    assert length(payload["works"]) > 300
    assert Enum.any?(payload["works"], &(&1["id"] == "ga-333"))
  end

  test "developer proofing endpoint retains source while reader endpoint does not", %{conn: conn} do
    reader_conn = get(conn, ~p"/api/catalog/ga-004/content")
    [reader_passage | _] = json_response(reader_conn, 200)["passages"]
    refute Map.has_key?(reader_passage, "source_text")

    proofing_conn = get(conn, ~p"/api/developer/catalog/ga-004/proofing")
    [proofing_passage | _] = json_response(proofing_conn, 200)["passages"]
    assert proofing_passage["source_text"] != proofing_passage["text"]
  end

  test "download manifest matches the exact response bytes and caching headers", %{conn: conn} do
    manifest = conn |> get(~p"/api/catalog/ga-001/manifest") |> json_response(200)
    assert [bundle] = manifest["bundles"]

    download = get(conn, ~p"/api/catalog/ga-001/content")
    payload = json_response(download, 200)
    checksum = :crypto.hash(:sha256, download.resp_body) |> Base.encode16(case: :lower)

    assert bundle["status"] == "available_on_demand"
    assert bundle["byte_size"] == byte_size(download.resp_body)
    assert bundle["checksum"] == checksum
    assert bundle["checksum_algorithm"] == "sha256"
    assert bundle["passages"] == Enum.map(payload["passages"], & &1["id"])
    assert get_resp_header(download, "x-content-sha256") == [checksum]

    assert get_resp_header(download, "content-disposition") == [
             "attachment; filename=\"ga-001.json\""
           ]

    assert get_resp_header(download, "content-length") == [
             Integer.to_string(byte_size(download.resp_body))
           ]

    assert [etag] = get_resp_header(download, "etag")

    cached =
      conn
      |> put_req_header("if-none-match", "W/" <> etag)
      |> get(~p"/api/catalog/ga-001/content")

    assert response(cached, 304) == ""
    assert get_resp_header(cached, "etag") == [etag]
  end

  test "unknown work IDs return 404", %{conn: conn} do
    assert conn |> get(~p"/api/catalog/ga-999/content") |> response(404) == ""
    assert conn |> get(~p"/api/catalog/ga-999/manifest") |> response(404) == ""
    assert conn |> get(~p"/api/catalog/ga-999") |> response(404) == ""
  end
end
