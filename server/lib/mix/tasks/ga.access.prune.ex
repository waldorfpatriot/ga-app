defmodule Mix.Tasks.Ga.Access.Prune do
  use Mix.Task

  @shortdoc "Erase expired private text and selection events"
  @impl true
  def run(_) do
    Mix.Task.run("app.start")

    unless GA.Access.repo_available?(),
      do: Mix.raise("Access backend unavailable; check database configuration")

    case GA.Access.prune_private_data() do
      {:ok, counts} -> Mix.shell().info(Jason.encode!(counts))
      {:error, _} -> Mix.raise("Access retention failed")
    end
  end
end
