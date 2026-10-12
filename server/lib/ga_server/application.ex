defmodule GA.Application do
  # See https://hexdocs.pm/elixir/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    repo_children =
      if System.get_env("GA_SKIP_REPO") in ["1", "true", "TRUE"] do
        []
      else
        [GA.Repo]
      end

    children =
      [GAWeb.Telemetry] ++
        repo_children ++
        [
          {DNSCluster, query: Application.get_env(:ga_server, :dns_cluster_query) || :ignore},
          {Phoenix.PubSub, name: GA.PubSub},
          GA.Access.RateLimiter,
          GA.Access.Retention,
          # Start a worker by calling: GA.Worker.start_link(arg)
          # {GA.Worker, arg},
          # Start to serve requests, typically the last entry
          GAWeb.Endpoint
        ]

    # See https://hexdocs.pm/elixir/Supervisor.html
    # for other strategies and supported options
    opts = [strategy: :one_for_one, name: GA.Supervisor]
    Supervisor.start_link(children, opts)
  end

  # Tell Phoenix to update the endpoint configuration
  # whenever the application is updated.
  @impl true
  def config_change(changed, _new, removed) do
    GAWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
