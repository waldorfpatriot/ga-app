# This file is responsible for configuring your application
# and its dependencies with the aid of the Config module.
#
# This configuration file is loaded before any dependency and
# is restricted to this project.

# General application configuration
import Config

config :ga_server,
  namespace: GA,
  ecto_repos: [GA.Repo],
  generators: [timestamp_type: :utc_datetime]

# Configures the endpoint
config :ga_server, GAWeb.Endpoint,
  url: [host: "localhost"],
  adapter: Bandit.PhoenixAdapter,
  render_errors: [
    formats: [json: GAWeb.ErrorJSON],
    layout: false
  ],
  pubsub_server: GA.PubSub,
  live_view: [signing_salt: "qU/Xt5Gm"]

# Configures Elixir's Logger
config :logger, :console,
  format: "$time $metadata[$level] $message\n",
  metadata: [:request_id]

# Use Jason for JSON parsing in Phoenix
config :phoenix, :json_library, Jason

# Free-access messages and recovery credentials must never appear in request logs.
config :phoenix, :filter_parameters, [
  "password",
  "message",
  "selected_text",
  "section_title",
  "section_id",
  "access_token",
  "recovery_code",
  "authorization"
]

config :ga_server, :access_retention_enabled, true

# Import environment specific config. This must remain at the bottom
# of this file so it overrides the configuration defined above.
import_config "#{config_env()}.exs"
