defmodule GAWeb.TextReportsControllerTest do
  use GAWeb.ConnCase, async: false
  import ExUnit.CaptureLog
  alias GA.Access
  @moduletag skip: System.get_env("GA_SKIP_REPO") in ["1", "true", "TRUE"]

  setup %{conn: conn} do
    {:ok, credentials} = Access.create_installation()
    %{conn: conn, credentials: credentials}
  end

  defp authenticated(conn, credentials),
    do: put_req_header(conn, "authorization", "Bearer " <> credentials.access_token)

  defp payload,
    do: %{
      report_id: Ecto.UUID.generate(),
      book_id: "ga-001",
      section_id: "chapter-1",
      selected_text: "PRIVATE_SELECTED_TEXT",
      message: "PRIVATE_CORRECTION_MESSAGE",
      platform: "ios"
    }

  test "authenticated inactive user can submit/retry; response is minimal and uncached", %{
    conn: conn,
    credentials: credentials
  } do
    params = payload()
    response = conn |> authenticated(credentials) |> post("/api/access/text-reports", params)
    data = json_response(response, 201)
    assert data == %{"status" => "received", "report_id" => params.report_id}
    assert get_resp_header(response, "cache-control") == ["no-store"]

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/text-reports", params)
           |> json_response(200) == data

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/text-reports", %{params | selected_text: "changed"})
           |> json_response(409) == %{"error" => "report_conflict"}

    assert conn
           |> authenticated(credentials)
           |> get("/api/access/status")
           |> json_response(200)
           |> Map.fetch!("active") == false
  end

  test "missing or invalid authorization and invalid payload return generic errors", %{
    conn: conn,
    credentials: credentials
  } do
    assert conn |> post("/api/access/text-reports", payload()) |> json_response(401) == %{
             "error" => "unauthorized"
           }

    assert conn
           |> put_req_header("authorization", "Bearer " <> String.duplicate("x", 43))
           |> post("/api/access/text-reports", payload())
           |> json_response(401) == %{"error" => "unauthorized"}

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/text-reports", %{payload() | selected_text: " "})
           |> json_response(422) == %{"error" => "invalid_report"}
  end

  test "private report data and bearer never appear in debug logs, including malformed JSON", %{
    conn: conn,
    credentials: credentials
  } do
    params = payload()

    log =
      capture_log([level: :debug], fn ->
        assert conn
               |> authenticated(credentials)
               |> post("/api/access/text-reports", params)
               |> json_response(201)

        assert conn
               |> authenticated(credentials)
               |> put_req_header("content-type", "application/json")
               |> post(
                 "/api/access/text-reports",
                 "{\"selected_text\":\"PRIVATE_MALFORMED_REPORT\" BROKEN}"
               )
               |> json_response(400) == %{"error" => "invalid_json"}
      end)

    for confidential <- [
          params.selected_text,
          params.message,
          "PRIVATE_MALFORMED_REPORT",
          credentials.access_token
        ],
        do: refute(log =~ confidential)

    assert Phoenix.Logger.filter_values(%{
             "selected_text" => params.selected_text,
             "section_title" => "private title",
             "section_id" => "private section"
           }) == %{
             "selected_text" => "[FILTERED]",
             "section_title" => "[FILTERED]",
             "section_id" => "[FILTERED]"
           }
  end

  test "ten submissions per installation per minute include retries", %{
    conn: conn,
    credentials: credentials
  } do
    params = payload()

    for index <- 1..10 do
      assert conn
             |> authenticated(credentials)
             |> post("/api/access/text-reports", params)
             |> json_response(if(index == 1, do: 201, else: 200))
    end

    response = conn |> authenticated(credentials) |> post("/api/access/text-reports", params)
    assert json_response(response, 429) == %{"error" => "rate_limited"}
    assert get_resp_header(response, "retry-after") == ["60"]
  end

  test "missing encryption key or repository returns 503 and leaves health operational", %{
    conn: conn,
    credentials: credentials
  } do
    key = Application.fetch_env!(:ga_server, :access_encryption_key)
    Application.delete_env(:ga_server, :access_encryption_key)
    on_exit(fn -> Application.put_env(:ga_server, :access_encryption_key, key) end)

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/text-reports", payload())
           |> json_response(503) == %{"error" => "access_unavailable"}

    Application.put_env(:ga_server, :access_encryption_key, key)
    old = System.get_env("GA_SKIP_REPO")
    System.put_env("GA_SKIP_REPO", "1")

    on_exit(fn ->
      if old, do: System.put_env("GA_SKIP_REPO", old), else: System.delete_env("GA_SKIP_REPO")
    end)

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/text-reports", payload())
           |> json_response(503) == %{"error" => "access_unavailable"}

    assert get(conn, "/api/health").status == 200
  end

  test "bounded JSON parser applies to reports", %{conn: conn, credentials: credentials} do
    assert conn
           |> authenticated(credentials)
           |> put_req_header("content-type", "application/json")
           |> post(
             "/api/access/text-reports",
             "{\"selected_text\":\"" <> String.duplicate("x", 70_000) <> "\"}"
           )
           |> json_response(413) == %{"error" => "request_too_large"}

    assert conn
           |> authenticated(credentials)
           |> put_req_header("content-type", "text/plain")
           |> post("/api/access/text-reports", "PRIVATE_BODY")
           |> json_response(415) == %{"error" => "json_required"}
  end
end
