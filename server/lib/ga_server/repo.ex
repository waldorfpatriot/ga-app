defmodule GA.Repo do
  use Ecto.Repo,
    otp_app: :ga_server,
    adapter: Ecto.Adapters.Postgres
end
