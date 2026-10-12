ExUnit.start()

unless System.get_env("GA_SKIP_REPO") in ["1", "true", "TRUE"] do
  Ecto.Adapters.SQL.Sandbox.mode(GA.Repo, :manual)
end
