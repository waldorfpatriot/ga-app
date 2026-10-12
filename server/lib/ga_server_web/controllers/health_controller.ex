defmodule GAWeb.HealthController do
  use GAWeb, :controller

  def show(conn, _params) do
    json(conn, %{
      ok: true,
      service: "ga_server",
      user_sync: "cloudkit_private_database",
      public_backend: "catalog_and_content_manifests"
    })
  end
end
