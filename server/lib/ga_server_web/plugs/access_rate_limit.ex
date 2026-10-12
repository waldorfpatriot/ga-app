defmodule GAWeb.Plugs.AccessRateLimit do
  import Plug.Conn
  alias GA.Access.RateLimiter
  alias GAWeb.Plugs.AccessGuard
  def init(options), do: options

  def call(conn, _) do
    policy =
      case {conn.method, conn.path_info} do
        {"POST", ["api", "access", "installations"]} ->
          {{:create, client_ip(conn)}, 20, :timer.hours(1)}

        {"POST", ["api", "access", "recover"]} ->
          {{:recover, client_ip(conn)}, 10, :timer.minutes(1)}

        {"POST", ["api", "access", "free-requests"]} ->
          {{:request, conn.assigns.access_installation.id}, 10, :timer.minutes(1)}

        {"POST", ["api", "access", "text-reports"]} ->
          {{:text_report, conn.assigns.access_installation.id}, 10, :timer.minutes(1)}

        {"POST", ["api", "access", "selections"]} ->
          {{:selection, conn.assigns.access_installation.id}, 120, :timer.minutes(1)}

        {"GET", ["api", "access", "statistics"]} ->
          {{:statistics, client_ip(conn)}, 120, :timer.minutes(1)}

        _ ->
          nil
      end

    if is_nil(policy) or allow?(policy) do
      conn
    else
      {_key, _limit, window} = policy

      conn
      |> put_resp_header("retry-after", Integer.to_string(div(window, 1000)))
      |> AccessGuard.error(429, "rate_limited")
    end
  end

  defp allow?({key, limit, window}), do: RateLimiter.allow?(key, limit, window)

  defp client_ip(conn) do
    # Only honor a single X-Real-IP from explicitly trusted reverse proxies.
    # The proxy must replace this header, never append client-provided values.
    if conn.remote_ip in Application.get_env(:ga_server, :access_trusted_proxy_ips, []) do
      case get_req_header(conn, "x-real-ip") do
        [value] ->
          case :inet.parse_address(String.to_charlist(value)) do
            {:ok, address} -> address
            _ -> conn.remote_ip
          end

        _ ->
          conn.remote_ip
      end
    else
      conn.remote_ip
    end
  end
end
