defmodule GA.Access do
  @moduledoc "Anonymous installation access, solidarity grants, and aggregate selection counts."
  import Ecto.Query
  alias GA.Repo
  alias GA.Access.{FreeRequest, Installation, MessageCipher, Selection, TextReports}
  @options ~w(annual supporter free)
  @window_days 90
  @message_retention_days 30

  def available? do
    repo_available?() and MessageCipher.configured?()
  end

  def repo_available? do
    System.get_env("GA_SKIP_REPO") not in ["1", "true", "TRUE"] and Process.whereis(Repo) != nil
  end

  def create_installation do
    token = secret()
    recovery = secret()

    installation =
      Repo.insert!(%Installation{
        token_hash: hash(token),
        recovery_hash: hash(recovery)
      })

    {:ok, credentials(installation, token) |> Map.put(:recovery_code, recovery)}
  end

  def authenticate(token) when is_binary(token) and byte_size(token) == 43 do
    Repo.get_by(Installation, token_hash: hash(token))
  end

  def authenticate(_), do: nil

  def recover(installation_id, recovery_code) do
    with {:ok, id} <- uuid(installation_id),
         true <- is_binary(recovery_code) and byte_size(recovery_code) == 43 do
      Repo.transaction(fn ->
        installation = Repo.one(from i in Installation, where: i.id == ^id, lock: "FOR UPDATE")
        # Both nonexistent installations and invalid secrets have identical responses.
        candidate_hash = hash(recovery_code)
        expected_hash = if installation, do: installation.recovery_hash, else: <<0::256>>

        if Plug.Crypto.secure_compare(candidate_hash, expected_hash) and installation do
          token = secret()

          updated =
            installation |> Ecto.Changeset.change(token_hash: hash(token)) |> Repo.update!()

          credentials(updated, token)
        else
          Repo.rollback(:unauthorized)
        end
      end)
    else
      _ -> {:error, :unauthorized}
    end
  end

  def status(%Installation{} = installation, now \\ DateTime.utc_now()) do
    starts_at = installation.free_starts_at
    expires_at = installation.free_expires_at

    active =
      not is_nil(expires_at) and DateTime.compare(starts_at, now) != :gt and
        DateTime.compare(expires_at, now) == :gt

    %{
      status: if(active, do: "granted", else: "inactive"),
      active: active,
      grant_kind: if(expires_at, do: "free", else: nil),
      starts_at: starts_at,
      expires_at: expires_at,
      revenuecat_app_user_id: installation.id
    }
  end

  def request_free(installation, request_id, message, now \\ DateTime.utc_now()) do
    with {:ok, request_id} <- uuid(request_id),
         {:ok, message} <- validate_message(message) do
      Repo.transaction(fn ->
        # Serialize requests for one installation: retries and simultaneous renewals
        # cannot create duplicate rows or add multiple years to the period.
        current =
          Repo.one!(from i in Installation, where: i.id == ^installation.id, lock: "FOR UPDATE")

        previous = Repo.get_by(FreeRequest, installation_id: current.id, request_id: request_id)

        if previous do
          {:replayed, status(current, now)}
        else
          proposed_expiry = calendar_year_from(now)

          ongoing =
            current.free_expires_at && DateTime.compare(current.free_expires_at, now) == :gt

          starts_at = if ongoing, do: current.free_starts_at, else: now

          expires_at =
            if ongoing && DateTime.compare(current.free_expires_at, proposed_expiry) == :gt,
              do: current.free_expires_at,
              else: proposed_expiry

          Repo.insert!(%FreeRequest{
            installation_id: current.id,
            request_id: request_id,
            message_ciphertext: MessageCipher.encrypt(message),
            starts_at: starts_at,
            expires_at: expires_at
          })

          updated =
            current
            |> Ecto.Changeset.change(free_starts_at: starts_at, free_expires_at: expires_at)
            |> Repo.update!()

          {:created, status(updated, now)}
        end
      end)
    end
  end

  def record_selection(installation, event_id, option, now \\ DateTime.utc_now()) do
    with {:ok, event_id} <- uuid(event_id), true <- option in @options do
      attributes = %{
        id: Ecto.UUID.generate(),
        installation_id: installation.id,
        event_id: event_id,
        option: option,
        inserted_at: now
      }

      {count, _} =
        Repo.insert_all(Selection, [attributes],
          on_conflict: :nothing,
          conflict_target: [:installation_id, :event_id]
        )

      case {count,
            Repo.get_by!(Selection, installation_id: installation.id, event_id: event_id).option} do
        {1, _} -> {:ok, :created}
        {0, ^option} -> {:ok, :replayed}
        {0, _} -> {:error, :conflict}
      end
    else
      false -> {:error, :invalid_option}
      error -> error
    end
  end

  def statistics(now \\ DateTime.utc_now()) do
    cutoff = DateTime.add(now, -@window_days * 86_400, :second)

    counts =
      Repo.all(
        from s in Selection,
          where: s.inserted_at >= ^cutoff and s.inserted_at <= ^now,
          group_by: s.option,
          select: {s.option, count(s.id)}
      )
      |> Map.new()

    total = counts |> Map.values() |> Enum.sum()

    options =
      Map.new(@options, fn option ->
        count = Map.get(counts, option, 0)

        {option,
         %{
           count: count,
           percentage: if(total == 0, do: 0.0, else: Float.round(count / total * 100, 1))
         }}
      end)

    %{window_days: @window_days, total: total, options: options}
  end

  def delete_installation(installation), do: Repo.delete(installation)

  def prune_private_data(now \\ DateTime.utc_now()) do
    message_cutoff = DateTime.add(now, -@message_retention_days * 86_400, :second)
    event_cutoff = DateTime.add(now, -@window_days * 86_400, :second)

    Repo.transaction(fn ->
      {messages, _} =
        Repo.update_all(
          from(r in FreeRequest,
            where: r.inserted_at <= ^message_cutoff and not is_nil(r.message_ciphertext)
          ),
          set: [message_ciphertext: nil, message_deleted_at: now]
        )

      {events, _} = Repo.delete_all(from(s in Selection, where: s.inserted_at < ^event_cutoff))

      %{
        messages_deleted: messages,
        selections_deleted: events,
        text_reports_deleted: TextReports.prune(now)
      }
    end)
  end

  @doc "Adds twelve calendar months in UTC; February 29 becomes February 28."
  def calendar_year_from(%DateTime{} = now) do
    year = now.year + 1
    day = min(now.day, Date.days_in_month(Date.new!(year, now.month, 1)))
    %{now | year: year, day: day}
  end

  defp credentials(installation, token),
    do: %{
      installation_id: installation.id,
      access_token: token,
      revenuecat_app_user_id: installation.id
    }

  defp secret, do: :crypto.strong_rand_bytes(32) |> Base.url_encode64(padding: false)
  defp hash(secret), do: :crypto.hash(:sha256, secret)

  defp uuid(value) do
    case Ecto.UUID.cast(value) do
      {:ok, id} -> {:ok, id}
      _ -> {:error, :invalid_id}
    end
  end

  defp validate_message(message) when is_binary(message) do
    message = String.trim(message)

    cond do
      message == "" -> {:error, :empty_message}
      byte_size(message) > 20_000 or String.length(message) > 5_000 -> {:error, :message_too_long}
      true -> {:ok, message}
    end
  end

  defp validate_message(_), do: {:error, :empty_message}
end
