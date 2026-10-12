defmodule GA.Access.TextReports do
  @moduledoc "Confidential corrections; no HTTP read endpoint or paid entitlement required."
  import Ecto.Query
  alias GA.Repo
  alias GA.Access.{Installation, MessageCipher, TextReport}
  @retention_days 180
  @fields ~w(report_id book_id section_id section_title selected_text selection_start selection_end message app_version app_build platform)

  def submit(%Installation{} = installation, params, now \\ DateTime.utc_now()) do
    with {:ok, payload} <- validate(params) do
      fingerprint = fingerprint(payload)

      Repo.transaction(fn ->
        # Serializing against installation deletion and concurrent retries also
        # makes a reused UUID with changed contents a deterministic conflict.
        current =
          Repo.one!(from i in Installation, where: i.id == ^installation.id, lock: "FOR UPDATE")

        previous =
          Repo.get_by(TextReport, installation_id: current.id, report_id: payload["report_id"])

        response = %{status: "received", report_id: payload["report_id"]}

        cond do
          is_nil(previous) ->
            Repo.insert!(%TextReport{
              installation_id: current.id,
              report_id: payload["report_id"],
              payload_ciphertext: payload |> Jason.encode!() |> MessageCipher.encrypt(),
              payload_fingerprint: fingerprint,
              inserted_at: now
            })

            {:created, response}

          Plug.Crypto.secure_compare(previous.payload_fingerprint, fingerprint) ->
            {:replayed, response}

          true ->
            Repo.rollback(:report_conflict)
        end
      end)
    end
  end

  @doc "Authorized operator use only. Returns at most 100 retained decrypted reports."
  def list_for_operator(limit \\ 100, offset \\ 0)
      when is_integer(limit) and limit in 1..100 and is_integer(offset) and offset >= 0 do
    Repo.all(
      from r in TextReport,
        where: not is_nil(r.payload_ciphertext),
        order_by: [asc: r.inserted_at, asc: r.id],
        limit: ^limit,
        offset: ^offset
    )
    |> Enum.map(fn report ->
      with plaintext when is_binary(plaintext) <- MessageCipher.decrypt(report.payload_ciphertext),
           {:ok, payload} <- Jason.decode(plaintext) do
        %{
          installation_id: report.installation_id,
          received_at: report.inserted_at,
          payload: payload
        }
      else
        _ -> raise "Text report decryption failed"
      end
    end)
  end

  def prune(now) do
    cutoff = DateTime.add(now, -@retention_days * 86_400, :second)

    {count, _} =
      Repo.update_all(
        from(r in TextReport,
          where: r.inserted_at <= ^cutoff and not is_nil(r.payload_ciphertext)
        ), set: [payload_ciphertext: nil, payload_deleted_at: now])

    count
  end

  # A keyed fingerprint permits conflict detection after erasure without leaving
  # an unkeyed digest from which short messages could be guessed offline.
  defp fingerprint(payload) do
    canonical = Enum.map(@fields, fn field -> [field, payload[field]] end) |> Jason.encode!()
    key = Application.fetch_env!(:ga_server, :access_encryption_key)
    :crypto.mac(:hmac, :sha256, key, "ga-text-report:v1:" <> canonical)
  end

  defp validate(params) when is_map(params) do
    with {:ok, report_id} <- Ecto.UUID.cast(params["report_id"]),
         true <-
           bounded?(params["book_id"], 100, 100) and
             Regex.match?(~r/\Aga-[a-z0-9]+(?:-[a-z0-9]+)*\z/, params["book_id"]),
         true <- bounded?(params["section_id"], 200, 800),
         true <- optional_bounded?(params["section_title"], 500, 2000),
         true <- bounded?(params["selected_text"], 8000, 32000),
         true <- valid_offsets?(params["selection_start"], params["selection_end"]),
         true <- optional_bounded?(params["message"], 2000, 8000),
         true <- optional_bounded?(params["app_version"], 50, 100),
         true <- optional_bounded?(params["app_build"], 50, 100),
         true <- params["platform"] in ~w(ios macos) do
      {:ok,
       Map.new(@fields, fn field ->
         {field, if(field == "report_id", do: report_id, else: params[field])}
       end)}
    else
      _ -> {:error, :invalid_report}
    end
  end

  defp validate(_), do: {:error, :invalid_report}

  defp bounded?(value, characters, bytes) do
    is_binary(value) and String.valid?(value) and byte_size(value) <= bytes and
      length(String.to_charlist(value)) <= characters and String.trim(value) != ""
  end

  defp optional_bounded?(nil, _, _), do: true
  defp optional_bounded?("", _, _), do: true

  defp optional_bounded?(value, characters, bytes) do
    is_binary(value) and String.valid?(value) and byte_size(value) <= bytes and
      length(String.to_charlist(value)) <= characters
  end

  defp valid_offsets?(nil, nil), do: true

  defp valid_offsets?(first, last),
    do:
      is_integer(first) and is_integer(last) and first >= 0 and last > first and
        last <= 2_147_483_647
end
