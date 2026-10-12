defmodule GA.Repo.Migrations.CreateTextReports do
  use Ecto.Migration

  def change do
    create table(:access_text_reports, primary_key: false) do
      add :id, :uuid, primary_key: true

      add :installation_id,
          references(:access_installations, type: :uuid, on_delete: :delete_all), null: false

      add :report_id, :uuid, null: false
      add :payload_ciphertext, :binary
      add :payload_fingerprint, :binary, null: false
      add :payload_deleted_at, :utc_datetime_usec
      timestamps(type: :utc_datetime_usec, updated_at: false)
    end

    create unique_index(:access_text_reports, [:installation_id, :report_id])
    create index(:access_text_reports, [:inserted_at])
  end
end
