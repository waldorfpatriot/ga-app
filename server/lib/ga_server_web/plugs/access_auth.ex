defmodule GAWeb.Plugs.AccessAuth do
  import Plug.Conn
  alias GAWeb.Plugs.AccessGuard
  def init(options), do: options

  def call(conn, _) do
    installation =
      case get_req_header(conn, "authorization") do
        ["Bearer " <> token] -> GA.Access.authenticate(token)
        _ -> nil
      end

    if installation do
      assign(conn, :access_installation, installation)
    else
      AccessGuard.error(conn, 401, "unauthorized")
    end
  rescue
    _ in [Postgrex.Error, DBConnection.ConnectionError] -> AccessGuard.unavailable(conn)
  catch
    :exit, _ -> AccessGuard.unavailable(conn)
  end
end
