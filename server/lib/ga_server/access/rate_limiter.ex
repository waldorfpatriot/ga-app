defmodule GA.Access.RateLimiter do
  @moduledoc "Bounded, ephemeral abuse protection; remote addresses are never persisted."
  use GenServer
  @max_entries 10_000
  @cleanup_interval 60_000

  def start_link(_), do: GenServer.start_link(__MODULE__, %{}, name: __MODULE__)

  def allow?(key, limit, window_ms),
    do: GenServer.call(__MODULE__, {:allow, key, limit, window_ms})

  @impl true
  def init(state) do
    Process.send_after(self(), :cleanup, @cleanup_interval)
    {:ok, state}
  end

  @impl true
  def handle_call({:allow, key, limit, window_ms}, _from, state) do
    now = System.monotonic_time(:millisecond)

    {count, expires_at} =
      case Map.get(state, key) do
        {count, expires_at} when expires_at > now -> {count, expires_at}
        _ -> {0, now + window_ms}
      end

    cond do
      count >= limit -> {:reply, false, state}
      not Map.has_key?(state, key) and map_size(state) >= @max_entries -> {:reply, false, state}
      true -> {:reply, true, Map.put(state, key, {count + 1, expires_at})}
    end
  end

  @impl true
  def handle_info(:cleanup, state) do
    now = System.monotonic_time(:millisecond)
    state = Map.reject(state, fn {_key, {_count, expires_at}} -> expires_at <= now end)
    Process.send_after(self(), :cleanup, @cleanup_interval)
    {:noreply, state}
  end
end
