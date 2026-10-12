defmodule GA.AccessTest do
  use GA.DataCase, async: true
  alias GA.Access
  alias GA.Access.{FreeRequest, Installation, MessageCipher, Selection}
  @moduletag skip: System.get_env("GA_SKIP_REPO") in ["1", "true", "TRUE"]

  setup do
    {:ok, credentials} = Access.create_installation()
    installation = Access.authenticate(credentials.access_token)
    %{installation: installation, credentials: credentials}
  end

  test "new installation has no access or trial, and credentials are only hashes", %{
    installation: installation,
    credentials: credentials
  } do
    assert installation.id == credentials.revenuecat_app_user_id
    assert byte_size(credentials.access_token) == 43
    assert byte_size(credentials.recovery_code) == 43
    assert installation.token_hash != credentials.access_token
    assert installation.recovery_hash != credentials.recovery_code
    refute inspect(installation) =~ Base.encode16(installation.token_hash)
    refute Access.authenticate("made-up-token")

    assert %{active: false, starts_at: nil, expires_at: nil, grant_kind: nil} =
             Access.status(installation)
  end

  test "clear request immediately grants a calendar year and encrypts trimmed text", %{
    installation: installation
  } do
    now = ~U[2026-10-09 10:23:45.123456Z]
    message = "Bitte ermögliche mir ein kostenloses Jahr."
    request_id = Ecto.UUID.generate()

    assert {:ok, {:created, status}} =
             Access.request_free(installation, request_id, "  #{message}  ", now)

    assert status.active
    assert status.grant_kind == "free"
    assert status.starts_at == now
    assert status.expires_at == ~U[2027-10-09 10:23:45.123456Z]
    stored = Repo.one!(FreeRequest)
    refute stored.message_ciphertext =~ message
    assert MessageCipher.decrypt(stored.message_ciphertext) == message
    assert stored.status == "granted"
  end

  test "leap-day calendar years end on February 28" do
    assert Access.calendar_year_from(~U[2028-02-29 18:04:22.123456Z]) ==
             ~U[2029-02-28 18:04:22.123456Z]
  end

  test "replayed request cannot extend access; new requests renew from now without stacking", %{
    installation: installation
  } do
    first = ~U[2026-10-09 12:00:00.000000Z]
    request_id = Ecto.UUID.generate()

    assert {:ok, {:created, original}} =
             Access.request_free(installation, request_id, "Bitte.", first)

    later = DateTime.add(first, 10, :day)

    assert {:ok, {:replayed, replayed}} =
             Access.request_free(installation, request_id, "Anderer Text.", later)

    assert replayed.expires_at == original.expires_at
    assert Repo.aggregate(FreeRequest, :count) == 1

    assert {:ok, {:created, renewed}} =
             Access.request_free(installation, Ecto.UUID.generate(), "Noch einmal bitte.", later)

    assert renewed.starts_at == first
    assert renewed.expires_at == Access.calendar_year_from(later)

    assert {:ok, {:created, same_day}} =
             Access.request_free(installation, Ecto.UUID.generate(), "Bitte.", later)

    assert same_day.expires_at == renewed.expires_at
  end

  test "expiry boundary is inactive, renewed expired access starts again", %{
    installation: installation
  } do
    first = ~U[2026-10-09 12:00:00.000000Z]

    {:ok, {:created, grant}} =
      Access.request_free(installation, Ecto.UUID.generate(), "Bitte.", first)

    stored = Repo.get!(Installation, installation.id)
    assert Access.status(stored, DateTime.add(grant.expires_at, -1, :second)).active
    refute Access.status(stored, grant.expires_at).active

    {:ok, {:created, renewed}} =
      Access.request_free(stored, Ecto.UUID.generate(), "Bitte.", grant.expires_at)

    assert renewed.starts_at == grant.expires_at
  end

  test "empty, missing, oversized messages and invalid identifiers do not persist grants", %{
    installation: installation
  } do
    for message <- [nil, "", " \n\t ", 123] do
      assert {:error, :empty_message} =
               Access.request_free(installation, Ecto.UUID.generate(), message)
    end

    assert {:error, :message_too_long} =
             Access.request_free(installation, Ecto.UUID.generate(), String.duplicate("ä", 5001))

    assert {:error, :invalid_id} = Access.request_free(installation, "not-a-uuid", "Bitte.")
    assert Repo.aggregate(FreeRequest, :count) == 0
    refute Access.status(Repo.get!(Installation, installation.id)).active
  end

  test "recovery rotates authentication, preserves grant, and remains reusable", %{
    installation: installation,
    credentials: credentials
  } do
    {:ok, {:created, granted}} = Access.request_free(installation, Ecto.UUID.generate(), "Bitte.")
    assert {:ok, recovered} = Access.recover(installation.id, credentials.recovery_code)
    assert recovered.installation_id == installation.id
    refute Access.authenticate(credentials.access_token)

    assert Access.status(Access.authenticate(recovered.access_token)).expires_at ==
             granted.expires_at

    assert {:ok, second} = Access.recover(installation.id, credentials.recovery_code)
    assert Access.authenticate(second.access_token)
    refute Access.authenticate(recovered.access_token)
    assert {:error, :unauthorized} = Access.recover(installation.id, String.duplicate("x", 43))

    assert {:error, :unauthorized} =
             Access.recover(Ecto.UUID.generate(), credentials.recovery_code)
  end

  test "statistics count genuine click events, deduplicate retries and exclude old/future records",
       %{installation: installation} do
    now = ~U[2026-10-09 12:00:00.000000Z]
    event_id = Ecto.UUID.generate()
    assert {:ok, :created} = Access.record_selection(installation, event_id, "annual", now)
    assert {:ok, :replayed} = Access.record_selection(installation, event_id, "annual", now)
    assert {:error, :conflict} = Access.record_selection(installation, event_id, "free", now)

    assert {:error, :invalid_option} =
             Access.record_selection(installation, Ecto.UUID.generate(), "paid", now)

    Access.record_selection(installation, Ecto.UUID.generate(), "supporter", now)

    Access.record_selection(
      installation,
      Ecto.UUID.generate(),
      "free",
      DateTime.add(now, -90, :day)
    )

    Access.record_selection(
      installation,
      Ecto.UUID.generate(),
      "free",
      DateTime.add(now, -91, :day)
    )

    Access.record_selection(
      installation,
      Ecto.UUID.generate(),
      "free",
      DateTime.add(now, 1, :day)
    )

    stats = Access.statistics(now)
    assert stats.total == 3
    assert stats.window_days == 90
    assert stats.options["annual"] == %{count: 1, percentage: 33.3}
    assert stats.options["supporter"].count == 1
    assert stats.options["free"].count == 1
    refute inspect(stats) =~ installation.id
  end

  test "retention erases only aged messages, keeps retry metadata and prunes aged clicks", %{
    installation: installation
  } do
    now = DateTime.utc_now()
    request_id = Ecto.UUID.generate()
    Access.request_free(installation, request_id, "Bitte.")
    stored = Repo.one!(FreeRequest)
    stored |> Ecto.Changeset.change(inserted_at: DateTime.add(now, -30, :day)) |> Repo.update!()

    Access.record_selection(
      installation,
      Ecto.UUID.generate(),
      "annual",
      DateTime.add(now, -91, :day)
    )

    Access.record_selection(installation, Ecto.UUID.generate(), "free", now)
    assert {:ok, %{messages_deleted: 1, selections_deleted: 1}} = Access.prune_private_data(now)
    erased = Repo.get!(FreeRequest, stored.id)
    assert erased.message_ciphertext == nil
    assert erased.message_deleted_at == now
    assert erased.request_id == request_id
    assert Repo.aggregate(Selection, :count) == 1
    assert {:ok, {:replayed, _}} = Access.request_free(installation, request_id, "Bitte.", now)
    assert Repo.get!(FreeRequest, stored.id).message_ciphertext == nil
  end

  test "deletion removes identity, grant, messages, events and recovery", %{
    installation: installation,
    credentials: credentials
  } do
    Access.request_free(installation, Ecto.UUID.generate(), "Bitte.")
    Access.record_selection(installation, Ecto.UUID.generate(), "free")
    assert {:ok, _} = Access.delete_installation(installation)
    assert Repo.aggregate(FreeRequest, :count) == 0
    assert Repo.aggregate(Selection, :count) == 0
    refute Access.authenticate(credentials.access_token)
    assert {:error, :unauthorized} = Access.recover(installation.id, credentials.recovery_code)
  end

  test "message cipher authenticates encrypted text and uses random nonces" do
    first = MessageCipher.encrypt("Bitte.")
    second = MessageCipher.encrypt("Bitte.")
    refute first == second
    assert MessageCipher.decrypt(first) == "Bitte."
    <<prefix::binary-size(29), _rest::binary>> = first
    assert MessageCipher.decrypt(prefix <> "changed") == :error
  end
end
