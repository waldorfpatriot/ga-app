defmodule GAWeb.Plugs.AccessGuard do
  @moduledoc "Fail closed for access APIs and prohibit caching credentials or private access state."
  import Plug.Conn
  def init(options), do: options

  def call(conn, _) do
    conn =
      conn
      |> put_resp_header("cache-control", "no-store")
      |> put_resp_header("pragma", "no-cache")
      |> put_resp_header("x-content-type-options", "nosniff")

    if GA.Access.available?(), do: conn, else: unavailable(conn)
  end

  def unavailable(conn), do: error(conn, 503, "access_unavailable")

  def error(conn, status, code) do
    conn
    |> put_resp_content_type("application/json")
    |> send_resp(status, Jason.encode!(%{error: code}))
    |> halt()
  end
end
