defmodule GA.Access.FreeRequest do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "access_free_requests" do
    field :installation_id, :binary_id
    field :request_id, :binary_id
    field :message_ciphertext, :binary, redact: true
    field :starts_at, :utc_datetime_usec
    field :expires_at, :utc_datetime_usec
    field :status, :string, default: "granted"
    field :message_deleted_at, :utc_datetime_usec
    timestamps(type: :utc_datetime_usec, updated_at: false)
  end
end
