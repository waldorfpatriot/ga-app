defmodule GAWeb.Router do
  use GAWeb, :router

  pipeline :api do
    plug :accepts, ["json"]
  end

  pipeline :access do
    plug GAWeb.Plugs.AccessGuard
  end

  pipeline :access_auth do
    plug GAWeb.Plugs.AccessAuth
  end

  pipeline :access_rate_limit do
    plug GAWeb.Plugs.AccessRateLimit
  end

  scope "/api/access", GAWeb do
    pipe_through [:api, :access, :access_rate_limit]
    post "/installations", AccessController, :create, log: false
    post "/recover", AccessController, :recover, log: false
    get "/statistics", AccessController, :statistics, log: false
  end

  scope "/api/access", GAWeb do
    pipe_through [:api, :access, :access_auth, :access_rate_limit]
    get "/status", AccessController, :status, log: false
    post "/free-requests", AccessController, :request_free, log: false
    post "/selections", AccessController, :selection, log: false
    post "/text-reports", AccessController, :text_report, log: false
    delete "/installation", AccessController, :delete, log: false
  end

  scope "/api", GAWeb do
    pipe_through :api

    get "/health", HealthController, :show
    get "/catalog", CatalogController, :index
    get "/catalog/:id", CatalogController, :show
    get "/catalog/:id/content", CatalogController, :content
    get "/catalog/:id/manifest", CatalogController, :manifest
    get "/developer/catalog", CatalogController, :developer_index
    get "/developer/catalog/:id", CatalogController, :developer_show
    get "/developer/catalog/:id/proofing", CatalogController, :proofing_content
  end
end
