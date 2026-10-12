defmodule GA.Access.Selection do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "access_selections" do
    field :installation_id, :binary_id
    field :event_id, :binary_id
    field :option, :string
    timestamps(type: :utc_datetime_usec, updated_at: false)
  end
end
