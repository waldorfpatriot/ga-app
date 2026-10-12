defmodule GAWeb.AccessControllerTest do
  use GAWeb.ConnCase, async: false
  import ExUnit.CaptureLog
  alias GA.Access
  @moduletag skip: System.get_env("GA_SKIP_REPO") in ["1", "true", "TRUE"]

  setup %{conn: conn} do
    # Independent ephemeral rate-limit identity for each test.
    value = System.unique_integer([:positive])

    conn = %{
      conn
      | remote_ip:
          {10, div(value, 65_536) |> rem(256), div(value, 256) |> rem(256), rem(value, 256)}
    }

    {:ok, credentials} = Access.create_installation()
    %{conn: conn, credentials: credentials}
  end

  defp authenticated(conn, credentials),
    do: put_req_header(conn, "authorization", "Bearer " <> credentials.access_token)

  test "creation credentials cannot be cached and status initially grants nothing", %{conn: conn} do
    response = post(conn, "/api/access/installations", %{})
    data = json_response(response, 201)
    assert data["installation_id"] == data["revenuecat_app_user_id"]
    assert data["recovery_code"]
    assert get_resp_header(response, "cache-control") == ["no-store"]

    response =
      conn
      |> put_req_header("authorization", "Bearer " <> data["access_token"])
      |> get("/api/access/status")

    assert %{"active" => false, "status" => "inactive", "starts_at" => nil, "expires_at" => nil} =
             json_response(response, 200)
  end

  test "all private endpoints require authentication; unknown credentials reveal nothing", %{
    conn: conn
  } do
    assert %{"error" => "unauthorized"} = conn |> get("/api/access/status") |> json_response(401)

    assert conn
           |> post("/api/access/free-requests", %{
             request_id: Ecto.UUID.generate(),
             message: "Bitte."
           })
           |> json_response(401)

    assert conn
           |> post("/api/access/selections", %{event_id: Ecto.UUID.generate(), option: "free"})
           |> json_response(401)

    assert conn |> delete("/api/access/installation") |> json_response(401)

    assert conn
           |> put_req_header("authorization", "Bearer " <> String.duplicate("x", 43))
           |> get("/api/access/status")
           |> json_response(401)
  end

  test "free request returns confirmed grant and retry is idempotent", %{
    conn: conn,
    credentials: credentials
  } do
    params = %{
      request_id: Ecto.UUID.generate(),
      message: "Bitte ermögliche mir ein kostenloses Jahr."
    }

    response = conn |> authenticated(credentials) |> post("/api/access/free-requests", params)
    data = json_response(response, 201)
    assert data["active"]
    assert data["status"] == "granted"
    assert data["grant_kind"] == "free"
    refute Map.has_key?(data, "message")

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/free-requests", params)
           |> json_response(200) == data

    assert conn |> authenticated(credentials) |> get("/api/access/status") |> json_response(200) ==
             data
  end

  test "validation errors cannot grant access", %{conn: conn, credentials: credentials} do
    response =
      conn
      |> authenticated(credentials)
      |> post("/api/access/free-requests", %{request_id: Ecto.UUID.generate(), message: "  "})

    assert json_response(response, 422) == %{"error" => "empty_message"}

    assert conn
           |> authenticated(credentials)
           |> get("/api/access/status")
           |> json_response(200)
           |> Map.fetch!("active") == false
  end

  test "public aggregate shows clicks while private messages are unavailable", %{
    conn: conn,
    credentials: credentials
  } do
    assert json_response(get(conn, "/api/access/statistics"), 200)["total"] == 0
    params = %{event_id: Ecto.UUID.generate(), option: "free"}

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/selections", params)
           |> json_response(201) == %{"status" => "recorded"}

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/selections", params)
           |> json_response(200) == %{"status" => "recorded"}

    stats = conn |> get("/api/access/statistics") |> json_response(200)
    assert stats["total"] == 1
    assert stats["options"]["free"] == %{"count" => 1, "percentage" => 100.0}
    refute Map.has_key?(stats, "installations")

    assert conn
           |> authenticated(credentials)
           |> post("/api/access/selections", %{params | option: "annual"})
           |> json_response(409) == %{"error" => "event_conflict"}
  end

  test "recovery gives uniform errors and rotates bearer; deletion revokes recovery", %{
    conn: conn,
    credentials: credentials
  } do
    params = %{
      installation_id: credentials.installation_id,
      recovery_code: credentials.recovery_code
    }

    recovered = conn |> post("/api/access/recover", params) |> json_response(200)
    assert recovered["installation_id"] == credentials.installation_id
    assert conn |> authenticated(credentials) |> get("/api/access/status") |> json_response(401)

    for invalid <- [
          %{params | recovery_code: String.duplicate("x", 43)},
          %{params | installation_id: Ecto.UUID.generate()}
        ] do
      assert conn |> post("/api/access/recover", invalid) |> json_response(401) == %{
               "error" => "unauthorized"
             }
    end

    response =
      conn
      |> put_req_header("authorization", "Bearer " <> recovered["access_token"])
      |> delete("/api/access/installation")

    assert response.status == 204
    assert response.resp_body == ""
    assert conn |> post("/api/access/recover", params) |> json_response(401)
  end

  test "private request text and recovery credentials are filtered from logs", %{
    conn: conn,
    credentials: credentials
  } do
    message = "PRIVATE_FINANCIAL_REQUEST_DO_NOT_LOG"

    output =
      capture_log([level: :debug], fn ->
        conn
        |> authenticated(credentials)
        |> post("/api/access/free-requests", %{request_id: Ecto.UUID.generate(), message: message})

        conn
        |> post("/api/access/recover", %{
          installation_id: credentials.installation_id,
          recovery_code: credentials.recovery_code
        })
      end)

    refute output =~ message
    refute output =~ credentials.access_token
    refute output =~ credentials.recovery_code

    assert Phoenix.Logger.filter_values(%{
             "message" => message,
             "recovery_code" => credentials.recovery_code
           }) == %{"message" => "[FILTERED]", "recovery_code" => "[FILTERED]"}
  end

  test "missing encryption key fails closed and leaves public catalog healthy", %{conn: conn} do
    key = Application.fetch_env!(:ga_server, :access_encryption_key)
    Application.delete_env(:ga_server, :access_encryption_key)
    on_exit(fn -> Application.put_env(:ga_server, :access_encryption_key, key) end)

    assert conn |> get("/api/access/statistics") |> json_response(503) == %{
             "error" => "access_unavailable"
           }

    assert conn |> post("/api/access/installations", %{}) |> json_response(503) == %{
             "error" => "access_unavailable"
           }

    assert get(conn, "/api/health").status == 200
  end

  test "GA_SKIP_REPO disables all access routes without breaking catalog health", %{conn: conn} do
    old = System.get_env("GA_SKIP_REPO")
    System.put_env("GA_SKIP_REPO", "1")

    on_exit(fn ->
      if old, do: System.put_env("GA_SKIP_REPO", old), else: System.delete_env("GA_SKIP_REPO")
    end)

    assert conn |> get("/api/access/statistics") |> json_response(503)
    assert get(conn, "/api/health").status == 200
  end

  test "rate limiter rejects repeated public installation creation", %{conn: conn} do
    for _ <- 1..20, do: assert(post(conn, "/api/access/installations", %{}).status == 201)
    response = post(conn, "/api/access/installations", %{})
    assert json_response(response, 429) == %{"error" => "rate_limited"}
    assert get_resp_header(response, "retry-after") == ["3600"]
  end

  test "malformed JSON returns generic errors and never logs raw private text", %{
    conn: conn,
    credentials: credentials
  } do
    message = "PRIVATE_MALFORMED_MESSAGE_DO_NOT_LOG"

    log =
      capture_log([level: :debug], fn ->
        response =
          conn
          |> authenticated(credentials)
          |> put_req_header("content-type", "application/json")
          |> post("/api/access/free-requests", "{\"message\":\"#{message}\" BROKEN}")

        assert json_response(response, 400) == %{"error" => "invalid_json"}
      end)

    refute log =~ message
  end

  test "access bodies are bounded and only JSON is accepted", %{
    conn: conn,
    credentials: credentials
  } do
    oversized =
      conn
      |> authenticated(credentials)
      |> put_req_header("content-type", "application/json")
      |> post(
        "/api/access/free-requests",
        "{\"message\":\"" <> String.duplicate("x", 70_000) <> "\"}"
      )

    assert json_response(oversized, 413) == %{"error" => "request_too_large"}

    unsupported =
      conn
      |> authenticated(credentials)
      |> put_req_header("content-type", "text/plain")
      |> post("/api/access/free-requests", "PRIVATE_PLAIN_BODY")

    assert json_response(unsupported, 415) == %{"error" => "json_required"}
  end
end
