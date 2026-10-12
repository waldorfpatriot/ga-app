defmodule GA.Access.Retention do
  @moduledoc "Hourly private-text erasure and selection-event retention."
  use GenServer
  require Logger
  @interval :timer.hours(1)

  def start_link(_), do: GenServer.start_link(__MODULE__, nil, name: __MODULE__)

  @impl true
  def init(state) do
    if Application.get_env(:ga_server, :access_retention_enabled, true),
      do: Process.send_after(self(), :prune, :timer.minutes(1))

    {:ok, state}
  end

  @impl true
  def handle_info(:prune, state) do
    if GA.Access.repo_available?() do
      try do
        GA.Access.prune_private_data()
      rescue
        _ -> Logger.warning("Access retention unavailable; will retry in one hour")
      catch
        :exit, _ -> Logger.warning("Access retention unavailable; will retry in one hour")
      end
    end

    Process.send_after(self(), :prune, @interval)
    {:noreply, state}
  end
end
