defmodule GA.Access.Installation do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "access_installations" do
    field :token_hash, :binary, redact: true
    field :recovery_hash, :binary, redact: true
    field :free_starts_at, :utc_datetime_usec
    field :free_expires_at, :utc_datetime_usec
    timestamps(type: :utc_datetime_usec)
  end
end
