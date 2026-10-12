defmodule GAWeb.CatalogController do
  use GAWeb, :controller

  alias GA.Catalog

  def index(conn, params) do
    json(conn, %{
      edition: "independent-public-domain",
      content_policy: Catalog.content_policy(),
      audience: "reader",
      works: Catalog.list_reader_works(params)
    })
  end

  def developer_index(conn, params) do
    json(conn, %{
      edition: "independent-public-domain",
      content_policy: Catalog.content_policy(),
      audience: "developer",
      works: Catalog.list_developer_works(params)
    })
  end

  def show(conn, %{"id" => id}) do
    case Catalog.get_reader_work(id) do
      nil -> send_resp(conn, :not_found, "")
      work -> json(conn, %{work: work})
    end
  end

  def developer_show(conn, %{"id" => id}) do
    case Catalog.get_developer_work(id) do
      nil -> send_resp(conn, :not_found, "")
      work -> json(conn, %{work: work})
    end
  end

  def manifest(conn, %{"id" => id}) do
    case Catalog.manifest(id) do
      nil -> send_resp(conn, :not_found, "")
      manifest -> json(conn, manifest)
    end
  end

  def content(conn, %{"id" => id}) do
    case Catalog.download(id) do
      nil ->
        send_resp(conn, :not_found, "")

      %{body: body, checksum: checksum, byte_size: byte_size} ->
        etag = "\"#{checksum}\""

        conn =
          conn
          |> put_resp_content_type("application/json")
          |> put_resp_header("content-disposition", "attachment; filename=\"#{id}.json\"")
          |> put_resp_header("cache-control", "public, max-age=0, must-revalidate")
          |> put_resp_header("etag", etag)
          |> put_resp_header("x-content-sha256", checksum)

        if Enum.any?(get_req_header(conn, "if-none-match"), &etag_matches?(&1, etag)) do
          send_resp(conn, :not_modified, "")
        else
          conn
          |> put_resp_header("content-length", Integer.to_string(byte_size))
          |> send_resp(:ok, body)
        end
    end
  end

  defp etag_matches?(header, etag) do
    header
    |> String.split(",")
    |> Enum.any?(fn value ->
      value = value |> String.trim() |> String.trim_leading("W/")
      value == etag or value == "*"
    end)
  end

  def proofing_content(conn, %{"id" => id}) do
    case Catalog.proofing_content(id) do
      nil -> send_resp(conn, :not_found, "")
      content -> json(conn, content)
    end
  end
end
