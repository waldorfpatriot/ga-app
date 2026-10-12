defmodule GA.Repo.Migrations.CreateAccess do
  use Ecto.Migration

  def change do
    create table(:access_installations, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :token_hash, :binary, null: false
      add :recovery_hash, :binary, null: false
      add :free_starts_at, :utc_datetime_usec
      add :free_expires_at, :utc_datetime_usec
      timestamps(type: :utc_datetime_usec)
    end

    create unique_index(:access_installations, [:token_hash])

    create constraint(:access_installations, :valid_free_period,
             check:
               "(free_starts_at IS NULL AND free_expires_at IS NULL) OR (free_starts_at IS NOT NULL AND free_expires_at > free_starts_at)"
           )

    create table(:access_free_requests, primary_key: false) do
      add :id, :uuid, primary_key: true

      add :installation_id,
          references(:access_installations, type: :uuid, on_delete: :delete_all), null: false

      add :request_id, :uuid, null: false
      add :message_ciphertext, :binary
      add :starts_at, :utc_datetime_usec, null: false
      add :expires_at, :utc_datetime_usec, null: false
      add :status, :string, null: false, default: "granted"
      add :message_deleted_at, :utc_datetime_usec
      timestamps(type: :utc_datetime_usec, updated_at: false)
    end

    create unique_index(:access_free_requests, [:installation_id, :request_id])
    create index(:access_free_requests, [:inserted_at])
    create constraint(:access_free_requests, :granted_only, check: "status = 'granted'")
    create constraint(:access_free_requests, :valid_grant_period, check: "expires_at > starts_at")

    create table(:access_selections, primary_key: false) do
      add :id, :uuid, primary_key: true

      add :installation_id,
          references(:access_installations, type: :uuid, on_delete: :delete_all), null: false

      add :event_id, :uuid, null: false
      add :option, :string, null: false
      timestamps(type: :utc_datetime_usec, updated_at: false)
    end

    create unique_index(:access_selections, [:installation_id, :event_id])
    create index(:access_selections, [:inserted_at, :option])

    create constraint(:access_selections, :valid_option,
             check: "option IN ('annual', 'supporter', 'free')"
           )
  end
end
