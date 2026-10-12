defmodule GAWeb.Plugs.AccessBodyParser do
  @moduledoc "Bound JSON input and suppress decoder snippets containing private request text."
  alias GAWeb.Plugs.AccessGuard

  def init(_) do
    Plug.Parsers.init(
      parsers: [:json],
      pass: [],
      length: 65_536,
      read_length: 65_536,
      json_decoder: Phoenix.json_library()
    )
  end

  def call(%{path_info: ["api", "access" | _]} = conn, options) do
    conn = AccessGuard.call(conn, [])
    if conn.halted, do: conn, else: parse(conn, options)
  end

  def call(conn, _), do: conn

  defp parse(conn, options) do
    Plug.Parsers.call(conn, options)
  rescue
    _ in [Plug.Parsers.ParseError, Plug.Conn.InvalidQueryError] ->
      AccessGuard.error(conn, 400, "invalid_json")

    _ in Plug.Parsers.RequestTooLargeError ->
      AccessGuard.error(conn, 413, "request_too_large")

    _ in Plug.Parsers.UnsupportedMediaTypeError ->
      AccessGuard.error(conn, 415, "json_required")
  end
end
