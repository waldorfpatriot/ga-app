defmodule GAWeb.AccessController do
  use GAWeb, :controller
  alias GA.Access
  alias GAWeb.Plugs.AccessGuard

  def create(conn, _params) do
    safely(conn, fn ->
      {:ok, credentials} = Access.create_installation()
      conn |> put_status(:created) |> json(credentials)
    end)
  end

  def recover(conn, params) do
    safely(conn, fn ->
      case Access.recover(params["installation_id"], params["recovery_code"]) do
        {:ok, credentials} -> json(conn, credentials)
        {:error, :unauthorized} -> AccessGuard.error(conn, 401, "unauthorized")
      end
    end)
  end

  def status(conn, _params), do: json(conn, Access.status(conn.assigns.access_installation))

  def request_free(conn, params) do
    safely(conn, fn ->
      case Access.request_free(
             conn.assigns.access_installation,
             params["request_id"],
             params["message"]
           ) do
        {:ok, {:created, status}} -> conn |> put_status(:created) |> json(status)
        {:ok, {:replayed, status}} -> json(conn, status)
        {:error, code} -> AccessGuard.error(conn, 422, Atom.to_string(code))
      end
    end)
  end

  def selection(conn, params) do
    safely(conn, fn ->
      case Access.record_selection(
             conn.assigns.access_installation,
             params["event_id"],
             params["option"]
           ) do
        {:ok, :created} -> conn |> put_status(:created) |> json(%{status: "recorded"})
        {:ok, :replayed} -> json(conn, %{status: "recorded"})
        {:error, :conflict} -> AccessGuard.error(conn, 409, "event_conflict")
        {:error, code} -> AccessGuard.error(conn, 422, Atom.to_string(code))
      end
    end)
  end

  def text_report(conn, params) do
    safely(conn, fn ->
      case GA.Access.TextReports.submit(conn.assigns.access_installation, params) do
        {:ok, {:created, response}} -> conn |> put_status(:created) |> json(response)
        {:ok, {:replayed, response}} -> json(conn, response)
        {:error, :report_conflict} -> AccessGuard.error(conn, 409, "report_conflict")
        {:error, :invalid_report} -> AccessGuard.error(conn, 422, "invalid_report")
      end
    end)
  end

  def statistics(conn, _params), do: safely(conn, fn -> json(conn, Access.statistics()) end)

  def delete(conn, _params) do
    safely(conn, fn ->
      {:ok, _} = Access.delete_installation(conn.assigns.access_installation)
      send_resp(conn, :no_content, "")
    end)
  end

  # Do not log request data, exception structs, credentials or database parameters.
  defp safely(conn, callback) do
    callback.()
  rescue
    _ in [Postgrex.Error, DBConnection.ConnectionError, Ecto.NoResultsError] ->
      AccessGuard.unavailable(conn)
  catch
    :exit, _ -> AccessGuard.unavailable(conn)
  end
end
