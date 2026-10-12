defmodule GA.Access.TextReport do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "access_text_reports" do
    field :installation_id, :binary_id
    field :report_id, :binary_id
    field :payload_ciphertext, :binary, redact: true
    field :payload_fingerprint, :binary, redact: true
    field :payload_deleted_at, :utc_datetime_usec
    timestamps(type: :utc_datetime_usec, updated_at: false)
  end
end
