import Config

# Configure your database
#
# The MIX_TEST_PARTITION environment variable can be used
# to provide built-in test partitioning in CI environment.
# Run `mix help test` for more information.
config :ga_server, GA.Repo,
  username: "postgres",
  password: "postgres",
  hostname: "localhost",
  database: "ga_server_test#{System.get_env("MIX_TEST_PARTITION")}",
  pool: Ecto.Adapters.SQL.Sandbox,
  pool_size: System.schedulers_online() * 2

# We don't run a server during test. If one is required,
# you can enable the server option below.
config :ga_server, GAWeb.Endpoint,
  http: [ip: {127, 0, 0, 1}, port: 4002],
  secret_key_base: "2nVGJkReCoJEVZ/86fMyekT9P6TFQa1NVIrqseT8eNOFnGiX13CQETCRydetdqFr",
  server: false

# Print only warnings and errors during test
config :logger, level: :warning

# Initialize plugs at runtime for faster test compilation
config :phoenix, :plug_init_mode, :runtime

config :ga_server, :access_encryption_key, <<0::256>>
config :ga_server, :access_retention_enabled, false
